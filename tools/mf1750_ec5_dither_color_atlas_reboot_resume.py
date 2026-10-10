#!/usr/bin/env python3
"""Resume only the unconsumed dither-atlas white action after an ESP reboot.

The original two-action runner deliberately requires both actions to share one
boot.  This facade handles one narrower observed state: ordinal 1 completed and
was manually observed, NVS still says READY/next ordinal 2, but a later reboot
cleared the volatile request/report counters.  It never replays ordinal 1 and
does not weaken the permanent claim, one-ARM, one-EXECUTE, or no-retry rules.

Importing, describing, validating, or building an authority is offline.  The
capture command performs four GETs only while J2 is confirmed OFF.  The run
command is the sole mutation entry and remains separately J2-ON gated.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence
import urllib.request


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_color_lab_physical_once as engine  # noqa: E402
from tools import mf1750_ec5_dither_color_atlas_campaign as campaign  # noqa: E402
from tools import mf1750_ec5_dither_color_atlas_containment_entry as entry  # noqa: E402
from tools import mf1750_ec5_dither_color_atlas_physical_once as physical  # noqa: E402


SCHEMA_VERSION = 1
DIAGNOSTIC_KIND = "mf1750-ec5-dither-color-atlas-reboot-resume-j2-off-diagnostic"
AUTHORITY_KIND = "mf1750-ec5-dither-color-atlas-reboot-resume-authority"
AUTHORIZATION_SUFFIX = (
    "__REBOOT_RESUME_CURSOR_2_NEW_BOOT_ZERO_VOLATILE_COUNTS"
    "__EXACT_ATLAS_RESULT_CLAIM_OBSERVATION"
    "__EXACT_J2_OFF_DIAGNOSTIC_AND_SAME_NEW_BOOT"
    "__NO_RETRY_NO_RECOVERY_NO_AUTOCHAIN"
)

RELEASE_FILE = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_DITHER_COLOR_ATLAS_RELEASE_OFFLINE_20260810_V1"
    / "dither-color-atlas-real-release.json"
)
ATLAS_RESULT_FILE = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_DITHER_COLOR_ATLAS_REBOUND_LIVE_20260818_V1"
    / "ordinal-01-atlas-result.json"
)
ATLAS_OBSERVATION_FILE = ATLAS_RESULT_FILE.with_name(
    "ordinal-01-atlas-observation.json"
)
ATLAS_ACTION_ID = "ef6458113f5f8d9bbbaf3d62dfbd1e4160b732b4bdbcdc4375097ef3013b0a2c"
WHITE_ACTION_ID = "35639e1fddd4cfbcccbaa529faa89a046496b171b695eb678737e6ed4a35eac3"
CLAIM_REGISTRY = physical.DEFAULT_CLAIM_REGISTRY
ATLAS_CLAIM_FILE = CLAIM_REGISTRY / f"{ATLAS_ACTION_ID}.json"
WHITE_CLAIM_FILE = CLAIM_REGISTRY / f"{WHITE_ACTION_ID}.json"
OUTPUT_DIR = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_DITHER_COLOR_ATLAS_REBOOT_RESUME_LIVE_20260818_V1"
)
DEFAULT_DIAGNOSTIC_FILE = OUTPUT_DIR / "j2-off-diagnostic.json"
DEFAULT_AUTHORITY_FILE = OUTPUT_DIR / "reboot-resume-authority.json"
DEFAULT_RESULT_FILE = OUTPUT_DIR / "ordinal-02-white-result.json"
DEFAULT_OBSERVATION_FILE = OUTPUT_DIR / "ordinal-02-white-observation.json"
SOURCE_FILE = Path(__file__).resolve()

EXPECTED_RELEASE_FILE_SHA256 = (
    "ec3e2d873badadef615b06b6a30948738ef80a4c4c3e31cbe24344454a037612"
)
EXPECTED_RELEASE_CANONICAL_SHA256 = (
    "68c5ffd09a9a46644e59493a985d21c2a035c5e21aba3324355ebd2eab5df7fe"
)
EXPECTED_ATLAS_RESULT_FILE_SHA256 = (
    "056fc4e3186938d095b07ed09ab0c8c08459a069cb8a0ca92724bef594a3d475"
)
EXPECTED_ATLAS_RESULT_CANONICAL_SHA256 = (
    "348ee35094d341b76ea681a2e426a021eeb0f47884fd60bd044207448d968c0b"
)
EXPECTED_ATLAS_OBSERVATION_FILE_SHA256 = (
    "00fcc331967abb32c40cf51d6bc872146fc89c1783a8fe033e575e672cfebfb9"
)
EXPECTED_ATLAS_OBSERVATION_CANONICAL_SHA256 = (
    "86b63ab0f590d8f91570da3aba5010bdc968573549b00fc2b21e96b145a96458"
)
EXPECTED_ATLAS_CLAIM_FILE_SHA256 = (
    "98ecff5a540fb76075f15088bf5297dde6aa5ea3622c4824bb7cf8799f2bff64"
)
EXPECTED_ATLAS_CLAIM_CANONICAL_SHA256 = (
    "d50628736a797b8cd281a6c344da3b83f350334c0d6e8a3caf5790d270be8738"
)
EXPECTED_ATLAS_BOOT_NONCE = "027ed5c3c397f64a"


RebootResumeError = physical.DitherColorAtlasPhysicalError
ReleaseContext = physical.ReleaseContext
Requester = physical.Requester

_BASE_VALIDATE_STATUS = engine._validate_status  # noqa: SLF001
_BASE_VALIDATE_PREFLIGHT_REPORT = engine._validate_preflight_report  # noqa: SLF001
_BASE_VALIDATE_TERMINAL_REPORT = engine._validate_terminal_report  # noqa: SLF001
_ACTIVE_AUTHORITY_ROOT: Mapping[str, Any] | None = None
_ACTIVE_AUTHORITY_FILE: Path | None = None


def _plain_file_reference(path: Path, *, label: str) -> dict[str, Any]:
    try:
        resolved = Path(path).resolve(strict=True)
        payload = resolved.read_bytes()
    except OSError as error:
        raise RebootResumeError(f"{label} cannot be read: {error}") from error
    return {
        "file": str(resolved),
        "bytes": len(payload),
        "file_sha256": campaign.sha256(payload),
    }


def _sealed_file_reference(
    path: Path,
    *,
    label: str,
    expected_file_sha256: str | None = None,
    expected_canonical_sha256: str | None = None,
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    try:
        resolved = Path(path).resolve(strict=True)
        payload = campaign._read_regular(resolved, label=label)  # noqa: SLF001
        root = campaign._decode(payload, label=label)  # noqa: SLF001
    except (OSError, campaign.DitherColorAtlasCampaignError) as error:
        raise RebootResumeError(f"{label} cannot be validated: {error}") from error
    integrity = root.get("integrity")
    unsigned = dict(root)
    unsigned.pop("integrity", None)
    canonical = campaign.sha256(unsigned)
    if not isinstance(integrity, Mapping) or dict(integrity) != {
        "canonical_sha256": canonical,
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }:
        raise RebootResumeError(f"{label} integrity differs")
    file_sha = campaign.sha256(payload)
    if expected_file_sha256 is not None and file_sha != expected_file_sha256:
        raise RebootResumeError(f"{label} file identity differs")
    if expected_canonical_sha256 is not None and canonical != expected_canonical_sha256:
        raise RebootResumeError(f"{label} canonical identity differs")
    return (
        {
            "file": str(resolved),
            "bytes": len(payload),
            "file_sha256": file_sha,
            "integrity_sha256": canonical,
        },
        root,
    )


def _exact_path(selected: Path, expected: Path, *, label: str) -> Path:
    try:
        resolved = Path(selected).resolve(strict=True)
        wanted = Path(expected).resolve(strict=True)
    except OSError as error:
        raise RebootResumeError(f"{label} cannot be resolved: {error}") from error
    if resolved != wanted:
        raise RebootResumeError(f"{label} is not the frozen exact path")
    return resolved


def _exact_target_path(selected: Path, expected: Path, *, label: str) -> Path:
    resolved = Path(selected).resolve()
    wanted = Path(expected).resolve()
    if resolved != wanted:
        raise RebootResumeError(f"{label} is not the frozen exact target")
    return resolved


def _fixed_lineage(context: ReleaseContext) -> dict[str, Any]:
    release_ref, _ = _sealed_file_reference(
        RELEASE_FILE,
        label="dither release",
        expected_file_sha256=EXPECTED_RELEASE_FILE_SHA256,
        expected_canonical_sha256=EXPECTED_RELEASE_CANONICAL_SHA256,
    )
    if (
        context.release_file != Path(RELEASE_FILE).resolve()
        or context.release_file_sha256 != EXPECTED_RELEASE_FILE_SHA256
        or context.release_canonical_sha256 != EXPECTED_RELEASE_CANONICAL_SHA256
    ):
        raise RebootResumeError("loaded dither release identity differs")
    result_ref, result_root = _sealed_file_reference(
        ATLAS_RESULT_FILE,
        label="completed Atlas result",
        expected_file_sha256=EXPECTED_ATLAS_RESULT_FILE_SHA256,
        expected_canonical_sha256=EXPECTED_ATLAS_RESULT_CANONICAL_SHA256,
    )
    observation_ref, observation_root = _sealed_file_reference(
        ATLAS_OBSERVATION_FILE,
        label="Atlas manual observation",
        expected_file_sha256=EXPECTED_ATLAS_OBSERVATION_FILE_SHA256,
        expected_canonical_sha256=EXPECTED_ATLAS_OBSERVATION_CANONICAL_SHA256,
    )
    claim_ref, claim_root = _sealed_file_reference(
        ATLAS_CLAIM_FILE,
        label="Atlas permanent claim",
        expected_file_sha256=EXPECTED_ATLAS_CLAIM_FILE_SHA256,
        expected_canonical_sha256=EXPECTED_ATLAS_CLAIM_CANONICAL_SHA256,
    )
    validated_result = physical.validate_result(
        context, ATLAS_RESULT_FILE, claim_registry=CLAIM_REGISTRY
    )
    validated_observation = physical.validate_observation(
        context,
        ATLAS_OBSERVATION_FILE,
        result_file=ATLAS_RESULT_FILE,
        claim_registry=CLAIM_REGISTRY,
    )
    if (
        dict(validated_result) != dict(result_root)
        or dict(validated_observation) != dict(observation_root)
        or result_root.get("ordinal") != 1
        or result_root.get("outcome") != "complete_pass"
        or result_root.get("action", {}).get("action_id") != ATLAS_ACTION_ID
        or result_root.get("preflight", {}).get("boot_nonce")
        != EXPECTED_ATLAS_BOOT_NONCE
        or observation_root.get("ordinal") != 1
        or observation_root.get("sequence_gate_pass") is not True
        or observation_root.get("action", {}).get("action_id") != ATLAS_ACTION_ID
        or claim_root.get("action", {}).get("action_id") != ATLAS_ACTION_ID
        or claim_root.get("state") != "permanently_claimed_before_first_arm_post"
        or context.actions[1].get("action_id") != WHITE_ACTION_ID
    ):
        raise RebootResumeError("exact completed Atlas lineage differs")
    return {
        "release": release_ref,
        "atlas_result": result_ref,
        "atlas_observation": observation_ref,
        "atlas_claim": claim_ref,
        "atlas_action_id": ATLAS_ACTION_ID,
        "atlas_boot_nonce": EXPECTED_ATLAS_BOOT_NONCE,
        "white_action_id": WHITE_ACTION_ID,
    }


def _reboot_validate_status(
    value: Any,
    *,
    action: Mapping[str, Any],
    phase: str,
    boot_nonce: str | None = None,
    expected_busy: int = 1,
) -> Mapping[str, Any]:
    """Validate ordinal 2 with volatile counters restarted from zero."""

    if int(action.get("ordinal", 0)) == 1:
        return _BASE_VALIDATE_STATUS(
            value,
            action=action,
            phase=phase,
            boot_nonce=boot_nonce,
            expected_busy=expected_busy,
        )
    if int(action.get("ordinal", 0)) != 2 or action.get("action_id") != WHITE_ACTION_ID:
        raise RebootResumeError("reboot-resume status accepts only exact ordinal 2")
    root = deepcopy(dict(value)) if isinstance(value, Mapping) else {}
    wanted_counts = {
        "ready": (0, 0, 0),
        "armed": (1, 0, 0),
        "terminal": (1, 1, 1),
    }
    if phase not in wanted_counts:
        raise RebootResumeError("reboot-resume status phase differs")
    fields = (
        "arm_request_count",
        "execute_request_count",
        "total_driver_call_count",
    )
    observed = tuple(root.get(key) for key in fields)
    if observed != wanted_counts[phase]:
        raise RebootResumeError(f"reboot-resume {phase} volatile counters differ")
    adjusted = deepcopy(root)
    for key in fields:
        adjusted[key] = int(adjusted[key]) + 1
    _BASE_VALIDATE_STATUS(
        adjusted,
        action=action,
        phase=phase,
        boot_nonce=boot_nonce,
        expected_busy=expected_busy,
    )
    return root


def _reboot_validate_preflight_report(
    value: Any, *, action: Mapping[str, Any], boot_nonce: str
) -> Mapping[str, Any]:
    if int(action.get("ordinal", 0)) == 1:
        return _BASE_VALIDATE_PREFLIGHT_REPORT(
            value, action=action, boot_nonce=boot_nonce
        )
    if int(action.get("ordinal", 0)) != 2 or action.get("action_id") != WHITE_ACTION_ID:
        raise RebootResumeError("reboot-resume report accepts only exact ordinal 2")
    fake_first = deepcopy(dict(action))
    fake_first["ordinal"] = 1
    _BASE_VALIDATE_PREFLIGHT_REPORT(value, action=fake_first, boot_nonce=boot_nonce)
    root = engine._identity(  # noqa: SLF001
        value,
        kind=f"{physical.DEVICE_KIND_PREFIX}-report",
        label="reboot-resume preflight report",
    )
    engine._keys(  # noqa: SLF001
        root,
        {
            "valid",
            "boot_nonce",
            "ordinal",
            "descriptor_id",
            "action_id",
            "terminal_state",
            "result",
            "error",
            "driver_called",
            "driver_call_count_for_action",
            "total_driver_call_count",
            "phase",
            "next_ordinal",
            "no_retry",
            "no_recovery",
        },
        label="reboot-resume preflight report",
    )
    expected = {
        "valid": False,
        "boot_nonce": boot_nonce,
        "ordinal": None,
        "descriptor_id": None,
        "action_id": None,
        "terminal_state": "NOT_EXECUTED",
        "result": False,
        "error": "no_execute_report",
        "driver_called": False,
        "driver_call_count_for_action": 0,
        "total_driver_call_count": 0,
        "phase": 0,
        "next_ordinal": 2,
        "no_retry": True,
        "no_recovery": True,
    }
    if any(root.get(key) != wanted for key, wanted in expected.items()):
        raise RebootResumeError("reboot-resume preflight report differs")
    return root


def _reboot_validate_terminal_report(
    value: Any, *, action: Mapping[str, Any], boot_nonce: str
) -> Mapping[str, Any]:
    if int(action.get("ordinal", 0)) == 1:
        return _BASE_VALIDATE_TERMINAL_REPORT(
            value, action=action, boot_nonce=boot_nonce
        )
    if int(action.get("ordinal", 0)) != 2 or action.get("action_id") != WHITE_ACTION_ID:
        raise RebootResumeError("reboot-resume terminal accepts only exact ordinal 2")
    root = deepcopy(dict(value)) if isinstance(value, Mapping) else {}
    if root.get("total_driver_call_count") != 1:
        raise RebootResumeError("reboot-resume terminal total driver count differs")
    adjusted = deepcopy(root)
    adjusted["total_driver_call_count"] = 2
    _BASE_VALIDATE_TERMINAL_REPORT(adjusted, action=action, boot_nonce=boot_nonce)
    return root


def _active_authority() -> tuple[Mapping[str, Any], Path]:
    if _ACTIVE_AUTHORITY_ROOT is None or _ACTIVE_AUTHORITY_FILE is None:
        raise RebootResumeError("reboot-resume authority is not active")
    return _ACTIVE_AUTHORITY_ROOT, _ACTIVE_AUTHORITY_FILE


def required_authorization(context: ReleaseContext, ordinal: int) -> str:
    if ordinal == 1:
        return entry.required_authorization(context, ordinal)
    if ordinal != 2:
        raise RebootResumeError("reboot-resume authorization accepts only ordinal 2")
    authority, _ = _active_authority()
    base = campaign.required_authorization(context.actions[1])
    return (
        f"{base}{AUTHORIZATION_SUFFIX}"
        f"__AUTHORITY_{authority['integrity']['canonical_sha256'].upper()}"
        f"__BOOT_{authority['diagnostic_boot_nonce'].upper()}"
    )


def _reboot_prior_gate(
    context: ReleaseContext,
    ordinal: int,
    *,
    prior_result_file: Path | None,
    prior_observation_file: Path | None,
    claim_registry: Path,
    confirm_no_intervening_visible_refresh: bool,
    j2_off_diagnostic_file: Path | None,
) -> dict[str, Any]:
    if ordinal != 2:
        raise RebootResumeError("reboot-resume entry refuses non-white ordinals")
    if not confirm_no_intervening_visible_refresh:
        raise RebootResumeError(
            "reboot-resume requires no-intervening-visible-refresh confirmation"
        )
    if (
        prior_result_file is None
        or prior_observation_file is None
        or j2_off_diagnostic_file is None
    ):
        raise RebootResumeError(
            "reboot-resume requires Atlas result, observation, and J2-off diagnostic"
        )
    _exact_path(prior_result_file, ATLAS_RESULT_FILE, label="prior Atlas result")
    _exact_path(
        prior_observation_file,
        ATLAS_OBSERVATION_FILE,
        label="prior Atlas observation",
    )
    if Path(claim_registry).resolve() != Path(CLAIM_REGISTRY).resolve():
        raise RebootResumeError("reboot-resume fixes the permanent claim registry")
    lineage = _fixed_lineage(context)
    diagnostic = validate_j2_off_diagnostic(
        context,
        j2_off_diagnostic_file,
        require_white_unclaimed=True,
    )
    authority, authority_file = _active_authority()
    authority_diag = authority.get("diagnostic")
    diagnostic_ref, _ = _sealed_file_reference(
        j2_off_diagnostic_file, label="reboot-resume J2-off diagnostic"
    )
    if (
        authority.get("diagnostic_boot_nonce") != diagnostic["boot_nonce"]
        or authority_diag != diagnostic_ref
        or authority.get("lineage") != lineage
    ):
        raise RebootResumeError("active reboot-resume authority binding differs")
    authority_ref, _ = _sealed_file_reference(
        authority_file, label="reboot-resume authority"
    )
    return {
        "kind": "exact_atlas_lineage_and_new_boot_cursor2_j2_off_diagnostic",
        "prior_ordinal": 1,
        "lineage": lineage,
        "diagnostic": diagnostic_ref,
        "authority": authority_ref,
        "previous_atlas_boot_nonce": EXPECTED_ATLAS_BOOT_NONCE,
        "required_same_boot_nonce": diagnostic["boot_nonce"],
        "boot_changed_after_atlas": True,
        "persistent_cursor_raw": 2,
        "persistent_next_ordinal": 2,
        "new_boot_ready_counts": {
            "arm_request_count": 0,
            "execute_request_count": 0,
            "total_driver_call_count": 0,
        },
        "new_boot_preflight_report": "NOT_EXECUTED",
        "live_no_intervening_visible_refresh_confirmed": True,
        "automatic_retry": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
    }


def install_overrides(
    authority: Mapping[str, Any] | None = None, authority_file: Path | None = None
) -> None:
    global _ACTIVE_AUTHORITY_FILE, _ACTIVE_AUTHORITY_ROOT
    entry.install_overrides()
    _ACTIVE_AUTHORITY_ROOT = (
        deepcopy(dict(authority)) if authority is not None else None
    )
    _ACTIVE_AUTHORITY_FILE = (
        Path(authority_file).resolve() if authority_file is not None else None
    )
    bindings = dict(physical._ENGINE_BINDINGS)  # noqa: SLF001
    bindings.update(
        {
            "_prior_gate": _reboot_prior_gate,
            "_validate_status": _reboot_validate_status,
            "_validate_preflight_report": _reboot_validate_preflight_report,
            "_validate_terminal_report": _reboot_validate_terminal_report,
            "required_authorization": required_authorization,
        }
    )
    physical._ENGINE_BINDINGS = bindings  # noqa: SLF001
    physical._dither_prior_gate = _reboot_prior_gate  # noqa: SLF001
    physical.required_authorization = required_authorization


def load_release(release_file: Path = RELEASE_FILE) -> ReleaseContext:
    _exact_path(release_file, RELEASE_FILE, label="dither release")
    entry.validate_containment_evidence()
    install_overrides()
    context = physical.load_release(release_file)
    _fixed_lineage(context)
    return context


def direct_http_request(
    base_url: str,
    path: str,
    *,
    method: str,
    headers: Mapping[str, str] | None,
    timeout: float,
) -> tuple[int, Mapping[str, Any]]:
    """Use an explicit empty proxy map; local device traffic must stay direct."""

    request = urllib.request.Request(
        base_url + path,
        headers=dict(headers or {}),
        method=method,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:  # noqa: S310
            status = response.getcode()
            payload = response.read(engine.MAX_JSON_BYTES + 1)
    except Exception as error:
        raise RebootResumeError(f"{method} {path} failed: {error}") from error
    if len(payload) > engine.MAX_JSON_BYTES:
        raise RebootResumeError(f"{method} {path} response is too large")
    return status, engine._decode(payload, label=f"{method} {path} response")  # noqa: SLF001


def capture_j2_off_diagnostic(
    context: ReleaseContext,
    base_url: str,
    *,
    diagnostic_file: Path,
    current_a: float,
    temperature_c: float,
    confirm_j2_off: bool,
    confirm_atlas_visible: bool,
    confirm_no_abnormality: bool,
    confirm_no_intervening_visible_refresh: bool,
    requester: Requester = direct_http_request,
    timeout: float = engine.DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not all(
        (
            confirm_j2_off,
            confirm_atlas_visible,
            confirm_no_abnormality,
            confirm_no_intervening_visible_refresh,
        )
    ):
        raise RebootResumeError("all reboot-resume J2-off confirmations are required")
    if (
        isinstance(current_a, bool)
        or not isinstance(current_a, (int, float))
        or not math.isfinite(float(current_a))
        or float(current_a) != 0.0
    ):
        raise RebootResumeError("J2-off panel current must be exactly 0 A")
    if (
        isinstance(temperature_c, bool)
        or not isinstance(temperature_c, (int, float))
        or not math.isfinite(float(temperature_c))
        or not engine.MIN_TEMPERATURE_C
        <= float(temperature_c)
        <= engine.MAX_TEMPERATURE_C
    ):
        raise RebootResumeError("temperature is outside 10..45 C")
    if WHITE_CLAIM_FILE.exists() or DEFAULT_RESULT_FILE.exists():
        raise RebootResumeError("white result or permanent claim already exists")
    _exact_target_path(
        diagnostic_file,
        DEFAULT_DIAGNOSTIC_FILE,
        label="reboot-resume J2-off diagnostic",
    )
    lineage = _fixed_lineage(context)
    target = engine._new_output_target(  # noqa: SLF001
        diagnostic_file, label="reboot-resume J2-off diagnostic"
    )
    with physical._bound_engine():  # noqa: SLF001
        audited = engine._AuditRequester(requester)  # noqa: SLF001
        snapshot = engine._fresh_preflight(  # noqa: SLF001
            context,
            base_url,
            2,
            audited,
            timeout=float(timeout),
            expected_busy=0,
        )
    if snapshot.boot_nonce == EXPECTED_ATLAS_BOOT_NONCE:
        raise RebootResumeError("diagnostic did not prove a new boot")
    status = snapshot.status
    report = snapshot.report
    evidence = engine._seal(  # noqa: SLF001
        {
            "schema_version": SCHEMA_VERSION,
            "kind": DIAGNOSTIC_KIND,
            "created_at": engine._now(),  # noqa: SLF001
            "lineage": lineage,
            "action": engine._action_reference(context, 2),  # noqa: SLF001
            "operator": {
                "j2_off": True,
                "current_a": 0.0,
                "temperature_c": float(temperature_c),
                "atlas_still_visible": True,
                "abnormal_sound_smell_or_heating": False,
                "no_intervening_visible_refresh": True,
            },
            "snapshot": snapshot.as_dict(),
            "previous_atlas_boot_nonce": EXPECTED_ATLAS_BOOT_NONCE,
            "boot_nonce": snapshot.boot_nonce,
            "boot_changed_after_atlas": True,
            "restart_cause_known": False,
            "persistent_cursor": {
                "cursor_raw": status["cursor_raw"],
                "next_ordinal": status["next_ordinal"],
                "persistent_key_present": status["persistent_key_present"],
                "state": status["state"],
                "phase": status["phase"],
            },
            "volatile_counts": {
                "arm_request_count": status["arm_request_count"],
                "execute_request_count": status["execute_request_count"],
                "total_driver_call_count": status["total_driver_call_count"],
            },
            "preflight_report": {
                "valid": report["valid"],
                "terminal_state": report["terminal_state"],
                "total_driver_call_count": report["total_driver_call_count"],
            },
            "network": {"get_requests": 4, "post_requests": 0},
            "transcript": audited.records,
            "white_claim_absent": True,
            "white_result_absent": True,
            "firmware_upload_performed": False,
            "reset_performed": False,
            "visible_refresh_authorized": False,
            "automatic_retry": False,
            "automatic_recovery": False,
            "automatic_chaining": False,
            "state": "new_boot_cursor2_zero_count_j2_off_diagnostic_pass",
        }
    )
    engine._write_new(target, evidence)  # noqa: SLF001
    return evidence


def validate_j2_off_diagnostic(
    context: ReleaseContext,
    diagnostic_file: Path,
    *,
    require_white_unclaimed: bool,
) -> dict[str, Any]:
    _exact_target_path(
        diagnostic_file,
        DEFAULT_DIAGNOSTIC_FILE,
        label="reboot-resume J2-off diagnostic",
    )
    diagnostic_ref, root = _sealed_file_reference(
        diagnostic_file, label="reboot-resume J2-off diagnostic"
    )
    del diagnostic_ref
    expected_fields = {
        "schema_version",
        "kind",
        "created_at",
        "lineage",
        "action",
        "operator",
        "snapshot",
        "previous_atlas_boot_nonce",
        "boot_nonce",
        "boot_changed_after_atlas",
        "restart_cause_known",
        "persistent_cursor",
        "volatile_counts",
        "preflight_report",
        "network",
        "transcript",
        "white_claim_absent",
        "white_result_absent",
        "firmware_upload_performed",
        "reset_performed",
        "visible_refresh_authorized",
        "automatic_retry",
        "automatic_recovery",
        "automatic_chaining",
        "state",
        "integrity",
    }
    engine._exact_keys(root, expected_fields, label="reboot-resume diagnostic")  # noqa: SLF001
    engine._timestamp(root["created_at"], label="reboot-resume diagnostic time")  # noqa: SLF001
    lineage = _fixed_lineage(context)
    operator = root["operator"]
    exact = {
        "schema_version": SCHEMA_VERSION,
        "kind": DIAGNOSTIC_KIND,
        "lineage": lineage,
        "action": engine._action_reference(context, 2),  # noqa: SLF001
        "previous_atlas_boot_nonce": EXPECTED_ATLAS_BOOT_NONCE,
        "boot_changed_after_atlas": True,
        "restart_cause_known": False,
        "persistent_cursor": {
            "cursor_raw": 2,
            "next_ordinal": 2,
            "persistent_key_present": True,
            "state": "ready",
            "phase": 0,
        },
        "volatile_counts": {
            "arm_request_count": 0,
            "execute_request_count": 0,
            "total_driver_call_count": 0,
        },
        "preflight_report": {
            "valid": False,
            "terminal_state": "NOT_EXECUTED",
            "total_driver_call_count": 0,
        },
        "network": {"get_requests": 4, "post_requests": 0},
        "white_claim_absent": True,
        "white_result_absent": True,
        "firmware_upload_performed": False,
        "reset_performed": False,
        "visible_refresh_authorized": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
        "state": "new_boot_cursor2_zero_count_j2_off_diagnostic_pass",
    }
    if any(root.get(key) != wanted for key, wanted in exact.items()):
        raise RebootResumeError("reboot-resume diagnostic semantics differ")
    if (
        not isinstance(operator, Mapping)
        or set(operator)
        != {
            "j2_off",
            "current_a",
            "temperature_c",
            "atlas_still_visible",
            "abnormal_sound_smell_or_heating",
            "no_intervening_visible_refresh",
        }
        or operator.get("j2_off") is not True
        or operator.get("current_a") != 0.0
        or isinstance(operator.get("temperature_c"), bool)
        or not isinstance(operator.get("temperature_c"), (int, float))
        or not math.isfinite(float(operator["temperature_c"]))
        or not engine.MIN_TEMPERATURE_C
        <= float(operator["temperature_c"])
        <= engine.MAX_TEMPERATURE_C
        or operator.get("atlas_still_visible") is not True
        or operator.get("abnormal_sound_smell_or_heating") is not False
        or operator.get("no_intervening_visible_refresh") is not True
    ):
        raise RebootResumeError("reboot-resume operator evidence differs")
    snapshot = root["snapshot"]
    preflight_value = engine.Preflight(
        snapshot["version"],
        snapshot["manifest"],
        snapshot["status"],
        snapshot["report"],
        snapshot["boot_nonce"],
    )
    with physical._bound_engine():  # noqa: SLF001
        engine._validate_version(preflight_value.version)  # noqa: SLF001
        engine._validate_manifest(preflight_value.manifest, context.actions)  # noqa: SLF001
        _reboot_validate_status(
            preflight_value.status,
            action=context.actions[1],
            phase="ready",
            expected_busy=0,
        )
        _reboot_validate_preflight_report(
            preflight_value.report,
            action=context.actions[1],
            boot_nonce=preflight_value.boot_nonce,
        )
    if (
        root["boot_nonce"] != preflight_value.boot_nonce
        or root["boot_nonce"] == EXPECTED_ATLAS_BOOT_NONCE
    ):
        raise RebootResumeError("reboot-resume diagnostic boot identity differs")
    transcript = root["transcript"]
    expected_paths = [
        campaign.ENDPOINTS[name] for name in ("version", "manifest", "status", "report")
    ]
    if (
        not isinstance(transcript, list)
        or len(transcript) != 4
        or [item.get("method") for item in transcript] != ["GET"] * 4
        or [item.get("path") for item in transcript] != expected_paths
        or [item.get("response") for item in transcript]
        != [
            preflight_value.version,
            preflight_value.manifest,
            preflight_value.status,
            preflight_value.report,
        ]
    ):
        raise RebootResumeError("reboot-resume diagnostic transcript differs")
    if require_white_unclaimed and (
        WHITE_CLAIM_FILE.exists() or DEFAULT_RESULT_FILE.exists()
    ):
        raise RebootResumeError("white action is no longer unclaimed")
    return dict(root)


def build_authority(
    context: ReleaseContext,
    diagnostic_file: Path,
    authority_file: Path,
) -> dict[str, Any]:
    _exact_target_path(
        diagnostic_file,
        DEFAULT_DIAGNOSTIC_FILE,
        label="reboot-resume J2-off diagnostic",
    )
    _exact_target_path(
        authority_file,
        DEFAULT_AUTHORITY_FILE,
        label="reboot-resume authority",
    )
    diagnostic = validate_j2_off_diagnostic(
        context, diagnostic_file, require_white_unclaimed=True
    )
    lineage = _fixed_lineage(context)
    diagnostic_ref, _ = _sealed_file_reference(
        diagnostic_file, label="reboot-resume J2-off diagnostic"
    )
    adapter_ref = _plain_file_reference(SOURCE_FILE, label="reboot-resume adapter")
    binding = {
        "kind": "dither-atlas-ordinal2-reboot-resume-binding-v1",
        "lineage": lineage,
        "diagnostic": diagnostic_ref,
        "diagnostic_boot_nonce": diagnostic["boot_nonce"],
        "adapter": adapter_ref,
        "action_id": WHITE_ACTION_ID,
        "scope": "ordinal2_white_only_new_boot_cursor2_zero_counts",
    }
    authority = engine._seal(  # noqa: SLF001
        {
            "schema_version": SCHEMA_VERSION,
            "kind": AUTHORITY_KIND,
            "created_at": engine._now(),  # noqa: SLF001
            "binding_id": campaign.sha256(binding),
            **binding,
            "constraints": {
                "j2_off_diagnostic_gets": 4,
                "j2_off_diagnostic_posts": 0,
                "fresh_j2_on_required": True,
                "same_new_boot_required": True,
                "maximum_arm_posts": 1,
                "maximum_execute_posts": 1,
                "maximum_driver_calls": 1,
                "automatic_retry": False,
                "automatic_recovery": False,
                "automatic_chaining": False,
                "firmware_flash": False,
                "esp32_reset": False,
            },
            "execution_authorized": False,
            "visible_refresh_authorized": 0,
            "state": "OFFLINE_READY_AWAITING_FRESH_J2_ON",
        }
    )
    target = engine._new_output_target(  # noqa: SLF001
        authority_file, label="reboot-resume authority"
    )
    engine._write_new(target, authority)  # noqa: SLF001
    return authority


def validate_authority(
    context: ReleaseContext,
    authority_file: Path,
    *,
    require_white_unclaimed: bool,
) -> dict[str, Any]:
    _exact_target_path(
        authority_file,
        DEFAULT_AUTHORITY_FILE,
        label="reboot-resume authority",
    )
    _, root = _sealed_file_reference(authority_file, label="reboot-resume authority")
    expected_fields = {
        "schema_version",
        "kind",
        "created_at",
        "binding_id",
        "lineage",
        "diagnostic",
        "diagnostic_boot_nonce",
        "adapter",
        "action_id",
        "scope",
        "constraints",
        "execution_authorized",
        "visible_refresh_authorized",
        "state",
        "integrity",
    }
    engine._exact_keys(root, expected_fields, label="reboot-resume authority")  # noqa: SLF001
    engine._timestamp(root["created_at"], label="reboot-resume authority time")  # noqa: SLF001
    diagnostic_path = Path(str(root.get("diagnostic", {}).get("file", "")))
    diagnostic = validate_j2_off_diagnostic(
        context,
        diagnostic_path,
        require_white_unclaimed=require_white_unclaimed,
    )
    lineage = _fixed_lineage(context)
    diagnostic_ref, _ = _sealed_file_reference(
        diagnostic_path, label="reboot-resume J2-off diagnostic"
    )
    adapter_ref = _plain_file_reference(SOURCE_FILE, label="reboot-resume adapter")
    binding = {
        "kind": "dither-atlas-ordinal2-reboot-resume-binding-v1",
        "lineage": lineage,
        "diagnostic": diagnostic_ref,
        "diagnostic_boot_nonce": diagnostic["boot_nonce"],
        "adapter": adapter_ref,
        "action_id": WHITE_ACTION_ID,
        "scope": "ordinal2_white_only_new_boot_cursor2_zero_counts",
    }
    expected = {
        "schema_version": SCHEMA_VERSION,
        "kind": AUTHORITY_KIND,
        "binding_id": campaign.sha256(binding),
        **binding,
        "constraints": {
            "j2_off_diagnostic_gets": 4,
            "j2_off_diagnostic_posts": 0,
            "fresh_j2_on_required": True,
            "same_new_boot_required": True,
            "maximum_arm_posts": 1,
            "maximum_execute_posts": 1,
            "maximum_driver_calls": 1,
            "automatic_retry": False,
            "automatic_recovery": False,
            "automatic_chaining": False,
            "firmware_flash": False,
            "esp32_reset": False,
        },
        "execution_authorized": False,
        "visible_refresh_authorized": 0,
        "state": "OFFLINE_READY_AWAITING_FRESH_J2_ON",
    }
    if any(root.get(key) != wanted for key, wanted in expected.items()):
        raise RebootResumeError("reboot-resume authority semantics differ")
    return dict(root)


def activate_authority(
    context: ReleaseContext,
    authority_file: Path,
    *,
    require_white_unclaimed: bool,
) -> dict[str, Any]:
    authority = validate_authority(
        context,
        authority_file,
        require_white_unclaimed=require_white_unclaimed,
    )
    install_overrides(authority, authority_file)
    return authority


def run_once(
    context: ReleaseContext,
    base_url: str,
    *,
    authority_file: Path,
    result_file: Path,
    temperature_c: float,
    confirm_j2_on: bool,
    confirm_electrical_normal: bool,
    confirm_atlas_visible: bool,
    confirm_no_intervening_visible_refresh: bool,
    requester: Requester = direct_http_request,
    poll_count: int = engine.DEFAULT_POLL_COUNT,
    poll_interval_seconds: float = engine.DEFAULT_POLL_INTERVAL_SECONDS,
    sleeper: Any = None,
) -> dict[str, Any]:
    if not confirm_atlas_visible:
        raise RebootResumeError("fresh J2-on report must confirm Atlas is visible")
    _exact_target_path(
        authority_file,
        DEFAULT_AUTHORITY_FILE,
        label="reboot-resume authority",
    )
    _exact_target_path(
        result_file,
        DEFAULT_RESULT_FILE,
        label="reboot-resume white result",
    )
    authority = activate_authority(
        context, authority_file, require_white_unclaimed=True
    )
    diagnostic_file = Path(str(authority["diagnostic"]["file"]))
    kwargs: dict[str, Any] = {
        "authorization": required_authorization(context, 2),
        "result_file": result_file,
        "claim_registry": CLAIM_REGISTRY,
        "prior_result_file": ATLAS_RESULT_FILE,
        "prior_observation_file": ATLAS_OBSERVATION_FILE,
        "j2_off_diagnostic_file": diagnostic_file,
        "confirm_no_intervening_visible_refresh": (
            confirm_no_intervening_visible_refresh
        ),
        "confirm_j2_on": confirm_j2_on,
        "confirm_electrical_normal": confirm_electrical_normal,
        "temperature_c": temperature_c,
        "requester": requester,
        "poll_count": poll_count,
        "poll_interval_seconds": poll_interval_seconds,
    }
    if sleeper is not None:
        kwargs["sleeper"] = sleeper
    return physical.run_once(context, base_url, 2, **kwargs)


def validate_result(
    context: ReleaseContext, authority_file: Path, result_file: Path
) -> dict[str, Any]:
    _exact_target_path(
        result_file,
        DEFAULT_RESULT_FILE,
        label="reboot-resume white result",
    )
    activate_authority(context, authority_file, require_white_unclaimed=False)
    return physical.validate_result(context, result_file, claim_registry=CLAIM_REGISTRY)


def finalize_observation(
    context: ReleaseContext,
    authority_file: Path,
    *,
    result_file: Path,
    observation_file: Path,
    operator_report: str,
    temperature_c: float,
    confirm_reference_preview_checked: bool,
    confirm_display_matches_reference: bool,
    confirm_no_unexpected_residual: bool,
    confirm_electrical_normal: bool,
    confirm_esp32_no_restart: bool,
    confirm_clean_white: bool,
) -> dict[str, Any]:
    _exact_target_path(
        result_file,
        DEFAULT_RESULT_FILE,
        label="reboot-resume white result",
    )
    _exact_target_path(
        observation_file,
        DEFAULT_OBSERVATION_FILE,
        label="reboot-resume white observation",
    )
    activate_authority(context, authority_file, require_white_unclaimed=False)
    return physical.finalize_observation(
        context,
        result_file=result_file,
        observation_file=observation_file,
        claim_registry=CLAIM_REGISTRY,
        operator_report=operator_report,
        temperature_c=temperature_c,
        confirm_reference_preview_checked=confirm_reference_preview_checked,
        confirm_display_matches_reference=confirm_display_matches_reference,
        confirm_no_unexpected_residual=confirm_no_unexpected_residual,
        confirm_electrical_normal=confirm_electrical_normal,
        confirm_esp32_no_restart=confirm_esp32_no_restart,
        confirm_clean_white=confirm_clean_white,
    )


def validate_observation(
    context: ReleaseContext,
    authority_file: Path,
    *,
    result_file: Path,
    observation_file: Path,
) -> dict[str, Any]:
    _exact_target_path(
        result_file,
        DEFAULT_RESULT_FILE,
        label="reboot-resume white result",
    )
    _exact_target_path(
        observation_file,
        DEFAULT_OBSERVATION_FILE,
        label="reboot-resume white observation",
    )
    activate_authority(context, authority_file, require_white_unclaimed=False)
    return physical.validate_observation(
        context,
        observation_file,
        result_file=result_file,
        claim_registry=CLAIM_REGISTRY,
    )


def describe(context: ReleaseContext, authority_file: Path) -> dict[str, Any]:
    authority = activate_authority(
        context, authority_file, require_white_unclaimed=True
    )
    return {
        "release_execution_eligible": context.execution_eligible,
        "action": engine._action_reference(context, 2),  # noqa: SLF001
        "authority": engine._file_reference(  # noqa: SLF001
            authority_file, label="reboot-resume authority"
        ),
        "diagnostic": authority["diagnostic"],
        "diagnostic_boot_nonce": authority["diagnostic_boot_nonce"],
        "previous_atlas_boot_nonce": EXPECTED_ATLAS_BOOT_NONCE,
        "persistent_cursor_required": 2,
        "new_boot_ready_counts_required": [0, 0, 0],
        "fresh_j2_on_required": True,
        "visible_refresh_authorized": False,
        "maximum_arm_posts": 1,
        "maximum_execute_posts": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--release", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("capture-j2-off", allow_abbrev=False)
    capture.add_argument("--base-url", required=True)
    capture.add_argument("--diagnostic", type=Path, required=True)
    capture.add_argument("--current-a", type=float, required=True)
    capture.add_argument("--temperature-c", type=float, required=True)
    capture.add_argument("--confirm-j2-off", action="store_true")
    capture.add_argument("--confirm-atlas-visible", action="store_true")
    capture.add_argument("--confirm-no-abnormality", action="store_true")
    capture.add_argument(
        "--confirm-no-intervening-visible-refresh", action="store_true"
    )
    validate_diag = commands.add_parser("validate-j2-off", allow_abbrev=False)
    validate_diag.add_argument("--diagnostic", type=Path, required=True)
    build = commands.add_parser("build-authority", allow_abbrev=False)
    build.add_argument("--diagnostic", type=Path, required=True)
    build.add_argument("--authority", type=Path, required=True)
    validate_auth = commands.add_parser("validate-authority", allow_abbrev=False)
    validate_auth.add_argument("--authority", type=Path, required=True)
    describe_parser = commands.add_parser("describe", allow_abbrev=False)
    describe_parser.add_argument("--authority", type=Path, required=True)
    run = commands.add_parser("run", allow_abbrev=False)
    run.add_argument("--base-url", required=True)
    run.add_argument("--authority", type=Path, required=True)
    run.add_argument("--result", type=Path, required=True)
    run.add_argument("--temperature-c", type=float, required=True)
    run.add_argument("--confirm-j2-on", action="store_true")
    run.add_argument("--confirm-electrical-normal", action="store_true")
    run.add_argument("--confirm-atlas-visible", action="store_true")
    run.add_argument("--confirm-no-intervening-visible-refresh", action="store_true")
    run.add_argument("--poll-count", type=int, default=engine.DEFAULT_POLL_COUNT)
    run.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=engine.DEFAULT_POLL_INTERVAL_SECONDS,
    )
    validate_result_parser = commands.add_parser("validate-result", allow_abbrev=False)
    validate_result_parser.add_argument("--authority", type=Path, required=True)
    validate_result_parser.add_argument("--result", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        context = load_release(args.release)
        if args.command == "capture-j2-off":
            output = capture_j2_off_diagnostic(
                context,
                args.base_url,
                diagnostic_file=args.diagnostic,
                current_a=args.current_a,
                temperature_c=args.temperature_c,
                confirm_j2_off=args.confirm_j2_off,
                confirm_atlas_visible=args.confirm_atlas_visible,
                confirm_no_abnormality=args.confirm_no_abnormality,
                confirm_no_intervening_visible_refresh=(
                    args.confirm_no_intervening_visible_refresh
                ),
            )
        elif args.command == "validate-j2-off":
            output = validate_j2_off_diagnostic(
                context, args.diagnostic, require_white_unclaimed=True
            )
        elif args.command == "build-authority":
            output = build_authority(context, args.diagnostic, args.authority)
        elif args.command == "validate-authority":
            output = validate_authority(
                context, args.authority, require_white_unclaimed=True
            )
        elif args.command == "describe":
            output = describe(context, args.authority)
        elif args.command == "run":
            output = run_once(
                context,
                args.base_url,
                authority_file=args.authority,
                result_file=args.result,
                temperature_c=args.temperature_c,
                confirm_j2_on=args.confirm_j2_on,
                confirm_electrical_normal=args.confirm_electrical_normal,
                confirm_atlas_visible=args.confirm_atlas_visible,
                confirm_no_intervening_visible_refresh=(
                    args.confirm_no_intervening_visible_refresh
                ),
                poll_count=args.poll_count,
                poll_interval_seconds=args.poll_interval_seconds,
            )
        else:
            output = validate_result(context, args.authority, args.result)
    except RebootResumeError as error:
        print(f"EC5 dither reboot-resume error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    if (
        args.command == "run"
        and isinstance(output, Mapping)
        and output.get("outcome") != "complete_pass"
    ):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
