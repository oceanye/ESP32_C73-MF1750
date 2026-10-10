#!/usr/bin/env python3
"""Execute exactly one authorized EC5 COLOR_LAB action.

The runner never advances to a second ordinal.  It verifies the immutable
release and prior result/observation chain, performs four read-only GETs,
durably claims the selected action, then permits at most one ARM and one
EXECUTE POST.  There is no automatic retry, recovery, or action chaining.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import threading
import time
from typing import Any, Callable, Mapping, Protocol, Sequence
import urllib.parse
import urllib.request
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_color_lab_campaign as campaign  # noqa: E402
from tools import mf1750_ec5_color_lab_contract as contract  # noqa: E402


SCHEMA_VERSION = 1
DEVICE_KIND_PREFIX = "mf1750-ec5-color-lab"
OBSERVATION_TEMPLATE_KIND = f"{DEVICE_KIND_PREFIX}-observation-template"
CLAIM_KIND = "mf1750-ec5-color-lab-permanent-host-claim"
RESULT_KIND = "mf1750-ec5-color-lab-physical-once-result"
OBSERVATION_KIND = "mf1750-ec5-color-lab-manual-observation"
J2_OFF_DIAGNOSTIC_KIND = "mf1750-ec5-color-lab-j2-off-diagnostic"
RECONCILIATION_KIND = "mf1750-ec5-color-lab-late-terminal-readback-reconciliation"
CLAIM_REGISTRY_ID = "workspace-mf1750-ec5-color-lab-claims-v1"
DEFAULT_CLAIM_REGISTRY = (
    REPO_ROOT / ".test-output" / "hardware" / ".mf1750_ec5_color_lab_claims"
)
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_POLL_COUNT = 80
DEFAULT_POLL_INTERVAL_SECONDS = 0.25
MAX_JSON_BYTES = 16 * 1024 * 1024
MIN_TEMPERATURE_C = 10.0
MAX_TEMPERATURE_C = 45.0
_NONCE_RE = re.compile(r"[0-9a-f]{16}\Z")
PREVIEW_FILES = {
    contract.ROLE_WHITE: REPO_ROOT
    / ".test-output/hardware/MF1750_EC5_EIGHTCODE_ATLAS_OFFLINE_20260809_V2_CORRECTED_PREVIEW/eightcode-white.preview.png",
    contract.ROLE_U07_ISOLATED: REPO_ROOT
    / ".test-output/hardware/MF1750_EC5_U07T_TECHNICAL_PREVIEW_OFFLINE_20260809_V1/U07T/u07t-pilot.preview.png",
    contract.ROLE_ATLAS: REPO_ROOT
    / ".test-output/hardware/MF1750_EC5_EIGHTCODE_ATLAS_OFFLINE_20260809_V2_CORRECTED_PREVIEW/eightcode-atlas.preview.png",
    contract.ROLE_U04_PRIMER: REPO_ROOT
    / ".test-output/hardware/MF1750_EC5_SIXSTATE_RELEASE_OFFLINE_20260809_V1/assets/U04/u04_primer.preview.png",
    contract.ROLE_U04_TARGET: REPO_ROOT
    / ".test-output/hardware/MF1750_EC5_SIXSTATE_RELEASE_OFFLINE_20260809_V1/assets/U04/u04_target.preview.png",
    contract.ROLE_U07_PRIMER: REPO_ROOT
    / ".test-output/hardware/MF1750_EC5_SIXSTATE_RELEASE_OFFLINE_20260809_V1/assets/U07/u07_primer.preview.png",
    contract.ROLE_U07_TARGET: REPO_ROOT
    / ".test-output/hardware/MF1750_EC5_SIXSTATE_RELEASE_OFFLINE_20260809_V1/assets/U07/u07_target.preview.png",
}

# Compatibility facades temporarily rebind this module's campaign-specific
# globals.  One engine-level lock must serialize every facade so bindings from
# different runners can never interleave in the same Python process.
_ENGINE_BINDING_LOCK = threading.RLock()


class ColorLabPhysicalError(RuntimeError):
    """A release, prior gate, device contract, or one-shot gate failed closed."""


class Requester(Protocol):
    def __call__(
        self,
        base_url: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]: ...


@dataclass(frozen=True)
class ReleaseContext:
    release_file: Path
    release_root: Mapping[str, Any]
    release_file_sha256: str
    release_canonical_sha256: str
    campaign_file: Path
    campaign_root: Mapping[str, Any]
    actions: tuple[Mapping[str, Any], ...]
    execution_eligible: bool
    formal_u07_registry: Path | None


@dataclass(frozen=True)
class Preflight:
    version: Mapping[str, Any]
    manifest: Mapping[str, Any]
    status: Mapping[str, Any]
    report: Mapping[str, Any]
    boot_nonce: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": deepcopy(dict(self.version)),
            "manifest": deepcopy(dict(self.manifest)),
            "status": deepcopy(dict(self.status)),
            "report": deepcopy(dict(self.report)),
            "boot_nonce": self.boot_nonce,
        }


def _now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise ColorLabPhysicalError(f"{label} must be RFC3339 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ColorLabPhysicalError(f"{label} is not RFC3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ColorLabPhysicalError(f"{label} lacks an offset")
    return parsed


def _keys(value: Any, required: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not required.issubset(value):
        raise ColorLabPhysicalError(f"{label} fields differ from contract")
    return value


def _exact_keys(value: Any, expected: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ColorLabPhysicalError(f"{label} fields differ from exact contract")
    return value


def _read(path: Path, *, label: str, maximum: int = MAX_JSON_BYTES) -> bytes:
    try:
        return campaign._read_regular(path, label=label, maximum=maximum)  # noqa: SLF001
    except campaign.ColorLabCampaignError as error:
        raise ColorLabPhysicalError(str(error)) from error


def _decode(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        return campaign._decode(payload, label=label)  # noqa: SLF001
    except campaign.ColorLabCampaignError as error:
        raise ColorLabPhysicalError(str(error)) from error


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result["integrity"] = {
        "canonical_sha256": campaign.sha256(value),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    return result


def _validate_seal(root: Mapping[str, Any], *, label: str) -> str:
    integrity = _exact_keys(
        root.get("integrity"),
        {"canonical_sha256", "scope"},
        label=f"{label}.integrity",
    )
    unsigned = dict(root)
    unsigned.pop("integrity")
    expected = {
        "canonical_sha256": campaign.sha256(unsigned),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    if dict(integrity) != expected:
        raise ColorLabPhysicalError(f"{label} integrity differs")
    return str(integrity["canonical_sha256"])


def _write_new(path: Path, value: Mapping[str, Any]) -> bytes:
    try:
        return campaign._write_new(path, value)  # noqa: SLF001
    except campaign.ColorLabCampaignError as error:
        raise ColorLabPhysicalError(str(error)) from error


def _release_reference(context: ReleaseContext) -> dict[str, Any]:
    return {
        "file": str(context.release_file),
        "file_sha256": context.release_file_sha256,
        "canonical_sha256": context.release_canonical_sha256,
    }


def load_release(release_file: Path) -> ReleaseContext:
    try:
        checked = campaign.validate_materialized_release(release_file)
    except campaign.ColorLabCampaignError as error:
        raise ColorLabPhysicalError(f"release validation failed: {error}") from error
    release_payload = _read(release_file, label="COLOR_LAB release")
    release_root = _decode(release_payload, label="COLOR_LAB release")
    campaign_file = Path(str(release_root["compiled_campaign"]["file"]))
    campaign_payload = _read(campaign_file, label="COLOR_LAB campaign")
    campaign_root = _decode(campaign_payload, label="COLOR_LAB campaign")
    actions = tuple(deepcopy(campaign_root["actions"]))
    formal_registry: Path | None = None
    if release_root["evidence_mode"] == campaign.REAL_MODE:
        formal_registry = Path(
            str(release_root["formal_u07_claim_absence"]["registry"])
        )
    return ReleaseContext(
        release_file=Path(release_file).resolve(),
        release_root=release_root,
        release_file_sha256=campaign.sha256(release_payload),
        release_canonical_sha256=str(checked["canonical_sha256"]),
        campaign_file=campaign_file.resolve(),
        campaign_root=campaign_root,
        actions=actions,
        execution_eligible=bool(checked["execution_eligible"]),
        formal_u07_registry=formal_registry,
    )


def _action(context: ReleaseContext, ordinal: int) -> Mapping[str, Any]:
    if isinstance(ordinal, bool) or not isinstance(ordinal, int):
        raise ColorLabPhysicalError("ordinal must be an integer")
    if not 1 <= ordinal <= len(context.actions):
        raise ColorLabPhysicalError("ordinal is outside the frozen campaign")
    action = context.actions[ordinal - 1]
    if action.get("ordinal") != ordinal:
        raise ColorLabPhysicalError("campaign ordinal table differs")
    return action


def _action_reference(context: ReleaseContext, ordinal: int) -> dict[str, Any]:
    action = _action(context, ordinal)
    return {
        "ordinal": ordinal,
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "round": action["round"],
        "branch": action["branch"],
        "frame_sha256": action["frame_sha256"],
        "cs1_dtm_sha256": action["cs1_dtm_sha256"],
        "cs2_dtm_sha256": action["cs2_dtm_sha256"],
    }


def _is_white_role(role: str) -> bool:
    """Support campaigns with more than one semantically white action role."""

    configured = getattr(contract, "WHITE_ROLES", (contract.ROLE_WHITE,))
    return role in configured


def required_authorization(context: ReleaseContext, ordinal: int) -> str:
    return campaign.required_authorization(_action(context, ordinal))


def _revalidate_real_release(context: ReleaseContext) -> None:
    try:
        checked = campaign.validate_materialized_release(context.release_file)
    except campaign.ColorLabCampaignError as error:
        raise ColorLabPhysicalError(f"live release replay failed: {error}") from error
    if (
        checked["execution_eligible"] is not True
        or checked["evidence_mode"] != campaign.REAL_MODE
        or context.execution_eligible is not True
        or context.release_root.get("execution_eligible") is not True
    ):
        raise ColorLabPhysicalError(
            "release is synthetic/offline and is not execution eligible"
        )


def _resolved_registry(path: Path, *, create: bool) -> Path:
    path = Path(path)
    try:
        if path.exists():
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise ColorLabPhysicalError(
                    "claim registry must be a non-symlink directory"
                )
            return path.resolve(strict=True)
        parent = path.parent.resolve(strict=True)
        if create:
            path.mkdir(mode=0o700, exist_ok=False)
            return path.resolve(strict=True)
        return parent / path.name
    except OSError as error:
        raise ColorLabPhysicalError(
            f"could not resolve claim registry: {error}"
        ) from error


def _claim_path(registry: Path, action_id: str) -> Path:
    return Path(registry) / f"{action_id}.json"


def _assert_absent(path: Path, *, label: str) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        raise ColorLabPhysicalError(f"could not inspect {label}: {error}") from error
    raise ColorLabPhysicalError(f"{label} already exists")


def _validate_execution_paths(
    *, result_file: Path, claim_registry: Path, action_id: str
) -> tuple[Path, Path]:
    result_file = Path(result_file)
    try:
        result_parent = result_file.parent.resolve(strict=True)
        parent_metadata = result_file.parent.lstat()
        if stat.S_ISLNK(parent_metadata.st_mode) or not stat.S_ISDIR(
            parent_metadata.st_mode
        ):
            raise ColorLabPhysicalError(
                "result parent must be an existing non-symlink directory"
            )
    except OSError as error:
        raise ColorLabPhysicalError(
            f"could not validate result parent: {error}"
        ) from error
    result_target = result_parent / result_file.name
    _assert_absent(result_target, label="COLOR_LAB result")
    registry = _resolved_registry(claim_registry, create=False)
    claim_target = _claim_path(registry, action_id)
    if os.path.normcase(str(result_target)) == os.path.normcase(str(claim_target)):
        raise ColorLabPhysicalError("result and permanent claim paths must differ")
    _assert_absent(claim_target, label="COLOR_LAB action claim")
    return result_target, registry


def _new_output_target(path: Path, *, label: str) -> Path:
    path = Path(path)
    try:
        parent_metadata = path.parent.lstat()
        parent = path.parent.resolve(strict=True)
        if stat.S_ISLNK(parent_metadata.st_mode) or not stat.S_ISDIR(
            parent_metadata.st_mode
        ):
            raise ColorLabPhysicalError(
                f"{label} parent must be an existing non-symlink directory"
            )
    except OSError as error:
        raise ColorLabPhysicalError(
            f"could not validate {label} parent: {error}"
        ) from error
    target = parent / path.name
    _assert_absent(target, label=label)
    return target


def _formal_u07_snapshot(context: ReleaseContext) -> dict[str, Any]:
    if context.formal_u07_registry is None:
        raise ColorLabPhysicalError("real release lacks formal U07 registry")
    try:
        return campaign._formal_u07_absence(context.formal_u07_registry)  # noqa: SLF001
    except campaign.ColorLabCampaignError as error:
        raise ColorLabPhysicalError(str(error)) from error


def _base_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ColorLabPhysicalError(
            "base URL must be an HTTP(S) origin without credentials/path/query/fragment"
        )
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def http_request(
    base_url: str,
    path: str,
    *,
    method: str,
    headers: Mapping[str, str] | None,
    timeout: float,
) -> tuple[int, Mapping[str, Any]]:
    request = urllib.request.Request(
        base_url + path,
        headers=dict(headers or {}),
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            status = response.getcode()
            payload = response.read(MAX_JSON_BYTES + 1)
    except Exception as error:
        raise ColorLabPhysicalError(f"{method} {path} failed: {error}") from error
    if len(payload) > MAX_JSON_BYTES:
        raise ColorLabPhysicalError(f"{method} {path} response is too large")
    return status, _decode(payload, label=f"{method} {path} response")


class _AuditRequester:
    def __init__(self, delegate: Requester) -> None:
        self.delegate = delegate
        self.records: list[dict[str, Any]] = []

    def __call__(
        self,
        base_url: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        status, response = self.delegate(
            base_url,
            path,
            method=method,
            headers=headers,
            timeout=timeout,
        )
        if not isinstance(status, int) or not isinstance(response, Mapping):
            raise ColorLabPhysicalError("requester returned a malformed response")
        record = {
            "method": method,
            "path": path,
            "headers": dict(sorted((headers or {}).items())),
            "status": status,
            "response": deepcopy(dict(response)),
        }
        self.records.append(record)
        if not 200 <= status < 300:
            raise ColorLabPhysicalError(f"{method} {path} returned HTTP {status}")
        return status, response

    @property
    def arm_posts(self) -> int:
        return sum(
            item["method"] == "POST" and item["path"] == campaign.ENDPOINTS["arm"]
            for item in self.records
        )

    @property
    def execute_posts(self) -> int:
        return sum(
            item["method"] == "POST" and item["path"] == campaign.ENDPOINTS["execute"]
            for item in self.records
        )


def _identity(value: Any, *, kind: str, label: str) -> Mapping[str, Any]:
    root = _keys(
        value,
        {
            "schema_version",
            "kind",
            "build_tag",
            "test_id",
            "campaign_id",
            "device_api_version",
            "identity_revision",
            "contract_id",
        },
        label=label,
    )
    expected = {
        "schema_version": contract.TOP_SCHEMA_VERSION,
        "kind": kind,
        "build_tag": contract.BUILD_TAG,
        "test_id": contract.TEST_ID,
        "campaign_id": contract.CAMPAIGN_ID,
        "device_api_version": contract.DEVICE_API_VERSION,
        "identity_revision": contract.IDENTITY_REVISION,
        "contract_id": contract.campaign_manifest()["contract_id"],
    }
    for key, wanted in expected.items():
        if root[key] != wanted:
            raise ColorLabPhysicalError(f"{label} {key} differs")
    return root


def _response_identity(value: Any, *, label: str) -> Mapping[str, Any]:
    root = _keys(
        value,
        {
            "build_tag",
            "test_id",
            "campaign_id",
            "device_api_version",
            "identity_revision",
            "contract_id",
        },
        label=label,
    )
    expected = {
        "build_tag": contract.BUILD_TAG,
        "test_id": contract.TEST_ID,
        "campaign_id": contract.CAMPAIGN_ID,
        "device_api_version": contract.DEVICE_API_VERSION,
        "identity_revision": contract.IDENTITY_REVISION,
        "contract_id": contract.campaign_manifest()["contract_id"],
    }
    for key, wanted in expected.items():
        if root[key] != wanted:
            raise ColorLabPhysicalError(f"{label} {key} differs")
    return root


def _device_action(action: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ordinal": action["ordinal"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "prior_static_action_id": action["action_identity_preimage"][
            "prior_static_action_id"
        ],
        "role": action["role"],
        "round": action["round"],
        "branch": action["branch"],
        "frame_sha256": action["frame_sha256"],
        "cs1_dtm_sha256": action["cs1_dtm_sha256"],
        "cs2_dtm_sha256": action["cs2_dtm_sha256"],
    }


def _validate_version(value: Any) -> Mapping[str, Any]:
    root = _identity(
        value, kind=f"{DEVICE_KIND_PREFIX}-version", label="device version"
    )
    required = {
        "classification",
        "action_count",
        "driver_api_version",
        "automatic_execute",
        "automatic_chaining",
        "startup_refresh",
        "raw_frame_ingress",
        "dither",
        "retry",
        "recovery",
        "nvs_contract",
    }
    _keys(root, required, label="device version")
    if root["action_count"] != campaign.ACTION_COUNT:
        raise ColorLabPhysicalError("device version action count differs")
    for key in (
        "automatic_execute",
        "automatic_chaining",
        "startup_refresh",
        "raw_frame_ingress",
        "dither",
        "retry",
        "recovery",
    ):
        if root[key] is not False:
            raise ColorLabPhysicalError(f"device version {key} must be false")
    nvs = _keys(root["nvs_contract"], {"namespace", "key"}, label="device NVS")
    if nvs["namespace"] != contract.NVS_NAMESPACE or nvs["key"] != contract.NVS_KEY:
        raise ColorLabPhysicalError("device NVS identity differs")
    return root


def _validate_manifest(
    value: Any, actions: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any]:
    root = _identity(
        value, kind=f"{DEVICE_KIND_PREFIX}-manifest", label="device manifest"
    )
    if root.get("action_count") != len(actions):
        raise ColorLabPhysicalError("device manifest action count differs")
    device_actions = root.get("actions")
    if not isinstance(device_actions, list) or len(device_actions) != len(actions):
        raise ColorLabPhysicalError("device manifest actions differ")
    for index, item in enumerate(device_actions):
        if item != _device_action(actions[index]):
            raise ColorLabPhysicalError(f"device manifest action {index + 1} differs")
    for key in (
        "automatic_chaining",
        "startup_refresh",
        "raw_frame_ingress",
        "dither",
        "retry",
        "recovery",
    ):
        if root.get(key) is not False:
            raise ColorLabPhysicalError(f"device manifest {key} must be false")
    return root


def _nonce(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _NONCE_RE.fullmatch(value) is None:
        raise ColorLabPhysicalError(f"{label} is malformed")
    return value


def _validate_status(
    value: Any,
    *,
    action: Mapping[str, Any],
    phase: str,
    boot_nonce: str | None = None,
    expected_busy: int = 1,
) -> Mapping[str, Any]:
    if expected_busy not in (0, 1):
        raise ColorLabPhysicalError("internal expected BUSY level differs")
    root = _identity(value, kind=f"{DEVICE_KIND_PREFIX}-status", label="device status")
    _keys(
        root,
        {
            "boot_nonce",
            "state",
            "phase",
            "phase_name",
            "cursor_raw",
            "next_ordinal",
            "current_action",
            "campaign_complete",
            "fixture_self_check_passed",
            "cursor_valid",
            "gpio_initialized",
            "busy",
            "rst",
            "cs",
            "cs2",
            "execute_pending",
            "arm_request_count",
            "execute_request_count",
            "total_driver_call_count",
            "persistent_key_present",
        },
        label="device status",
    )
    nonce = _nonce(root["boot_nonce"], label="device boot nonce")
    if boot_nonce is not None and nonce != boot_nonce:
        raise ColorLabPhysicalError("device boot nonce changed")
    if (
        root["fixture_self_check_passed"] is not True
        or root["gpio_initialized"] is not True
    ):
        raise ColorLabPhysicalError("device fixture/GPIO self-check failed")
    if root["cursor_valid"] is not True:
        raise ColorLabPhysicalError("device persistent cursor is invalid")
    if {key: root[key] for key in ("busy", "rst", "cs", "cs2")} != {
        "busy": expected_busy,
        "rst": 0,
        "cs": 0,
        "cs2": 0,
    }:
        raise ColorLabPhysicalError("device GPIO is not in the exact safe idle state")
    ordinal = int(action["ordinal"])
    if phase == "ready":
        expected = {
            "state": "ready",
            "phase": 0,
            "phase_name": "READY",
            "next_ordinal": ordinal,
            "current_action": None,
            "campaign_complete": False,
            "execute_pending": False,
        }
    elif phase == "armed":
        expected = {
            "state": "armed",
            "phase": 1,
            "phase_name": "ARMED",
            "next_ordinal": ordinal,
            "current_action": _device_action(action),
            "campaign_complete": False,
            "execute_pending": False,
        }
    elif phase == "terminal":
        final = ordinal == campaign.ACTION_COUNT
        expected = {
            "state": "complete" if final else "ready",
            "phase": 0,
            "phase_name": "READY",
            "next_ordinal": ordinal + 1,
            "current_action": None,
            "campaign_complete": final,
            "execute_pending": False,
        }
    else:
        raise ColorLabPhysicalError("internal status phase differs")
    for key, wanted in expected.items():
        if root[key] != wanted:
            raise ColorLabPhysicalError(f"device {phase} status {key} differs")
    expected_cursor = expected["phase"] * 256 + expected["next_ordinal"]
    if root["cursor_raw"] != expected_cursor:
        raise ColorLabPhysicalError(f"device {phase} cursor encoding differs")
    expected_key_present = not (phase == "ready" and ordinal == 1)
    if root["persistent_key_present"] is not expected_key_present:
        raise ColorLabPhysicalError(f"device {phase} persistent-key presence differs")
    for key in (
        "arm_request_count",
        "execute_request_count",
        "total_driver_call_count",
    ):
        if (
            isinstance(root[key], bool)
            or not isinstance(root[key], int)
            or root[key] < 0
        ):
            raise ColorLabPhysicalError(f"device status {key} is malformed")
    prior_count = ordinal - 1
    expected_counts = {
        "ready": {
            "arm_request_count": prior_count,
            "execute_request_count": prior_count,
            "total_driver_call_count": prior_count,
        },
        "armed": {
            "arm_request_count": ordinal,
            "execute_request_count": prior_count,
            "total_driver_call_count": prior_count,
        },
        "terminal": {
            "arm_request_count": ordinal,
            "execute_request_count": ordinal,
            "total_driver_call_count": ordinal,
        },
    }[phase]
    for key, wanted in expected_counts.items():
        if root[key] != wanted:
            raise ColorLabPhysicalError(
                f"device {phase} status {key} cumulative count differs"
            )
    return root


def _validate_preflight_report(
    value: Any, *, action: Mapping[str, Any], boot_nonce: str
) -> Mapping[str, Any]:
    root = _identity(
        value, kind=f"{DEVICE_KIND_PREFIX}-report", label="device preflight report"
    )
    if root.get("boot_nonce") != boot_nonce or not isinstance(root.get("valid"), bool):
        raise ColorLabPhysicalError("device preflight report identity differs")
    ordinal = int(action["ordinal"])
    if ordinal == 1:
        if root["valid"] is not False or root.get("terminal_state") != "NOT_EXECUTED":
            raise ColorLabPhysicalError(
                "ordinal 1 preflight report is not NOT_EXECUTED"
            )
    else:
        previous = contract.DESCRIPTORS[ordinal - 2]
        if (
            root["valid"] is not True
            or root.get("terminal_state") != "COMPLETE"
            or root.get("ordinal") != ordinal - 1
            or root.get("action_id") != previous["hardware_action_id"]
            or root.get("descriptor_id") != previous["descriptor_id"]
            or root.get("result") is not True
        ):
            raise ColorLabPhysicalError(
                "preflight report is not the prior COMPLETE action"
            )
    return root


def _fresh_preflight(
    context: ReleaseContext,
    base_url: str,
    ordinal: int,
    requester: _AuditRequester,
    *,
    timeout: float,
    expected_busy: int = 1,
) -> Preflight:
    action = _action(context, ordinal)
    origin = _base_url(base_url)

    def get(name: str) -> Mapping[str, Any]:
        return requester(
            origin,
            campaign.ENDPOINTS[name],
            method="GET",
            headers=None,
            timeout=timeout,
        )[1]

    version = _validate_version(get("version"))
    manifest = _validate_manifest(get("manifest"), context.actions)
    status = _validate_status(
        get("status"), action=action, phase="ready", expected_busy=expected_busy
    )
    boot_nonce = str(status["boot_nonce"])
    report = _validate_preflight_report(
        get("report"), action=action, boot_nonce=boot_nonce
    )
    if len(requester.records) != 4 or any(
        item["method"] != "GET" for item in requester.records
    ):
        raise ColorLabPhysicalError("preflight was not exactly four GETs")
    return Preflight(version, manifest, status, report, boot_nonce)


def preflight(
    context: ReleaseContext,
    base_url: str,
    ordinal: int,
    *,
    requester: Requester = http_request,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Preflight:
    """Perform four GETs only; synthetic releases fail before requester use."""

    _revalidate_real_release(context)
    _formal_u07_snapshot(context)
    audited = _AuditRequester(requester)
    return _fresh_preflight(context, base_url, ordinal, audited, timeout=timeout)


def diagnose_j2_off(
    context: ReleaseContext,
    base_url: str,
    *,
    evidence_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    confirm_j2_off: bool,
    requester: Requester = http_request,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Seal four GETs after the one planned flash while J2 is physically off."""

    _revalidate_real_release(context)
    if not confirm_j2_off:
        raise ColorLabPhysicalError("J2-off diagnostic requires explicit confirmation")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(float(timeout))
        or timeout <= 0
    ):
        raise ColorLabPhysicalError("diagnostic timeout is invalid")
    target = _new_output_target(evidence_file, label="J2-off diagnostic evidence")
    action = _action(context, 1)
    registry = _resolved_registry(claim_registry, create=False)
    _assert_absent(
        _claim_path(registry, str(action["action_id"])),
        label="ordinal 1 claim",
    )
    formal = _formal_u07_snapshot(context)
    audited = _AuditRequester(requester)
    snapshot = _fresh_preflight(
        context,
        base_url,
        1,
        audited,
        timeout=float(timeout),
        expected_busy=0,
    )
    evidence = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": J2_OFF_DIAGNOSTIC_KIND,
            "created_at": _now(),
            "release": _release_reference(context),
            "firmware_binary": deepcopy(
                dict(context.release_root["firmware"]["binary"])
            ),
            "action": _action_reference(context, 1),
            "j2_driver_power_confirmed_off": True,
            "snapshot": snapshot.as_dict(),
            "boot_nonce": snapshot.boot_nonce,
            "formal_u07_claim_absence": formal,
            "network": {"get_requests": 4, "post_requests": 0},
            "transcript": audited.records,
            "claim_created": False,
            "visible_refresh_authorized": False,
            "firmware_upload_performed_by_this_tool": False,
            "state": "j2_off_same_boot_four_get_diagnostic_pass",
        }
    )
    _write_new(target, evidence)
    return evidence


def validate_j2_off_diagnostic(
    context: ReleaseContext,
    evidence_file: Path,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    _revalidate_real_release(context)
    payload = _read(evidence_file, label="J2-off diagnostic evidence")
    root = _decode(payload, label="J2-off diagnostic evidence")
    expected_fields = {
        "schema_version",
        "kind",
        "created_at",
        "release",
        "firmware_binary",
        "action",
        "j2_driver_power_confirmed_off",
        "snapshot",
        "boot_nonce",
        "formal_u07_claim_absence",
        "network",
        "transcript",
        "claim_created",
        "visible_refresh_authorized",
        "firmware_upload_performed_by_this_tool",
        "state",
        "integrity",
    }
    _exact_keys(root, expected_fields, label="J2-off diagnostic evidence")
    _validate_seal(root, label="J2-off diagnostic evidence")
    _timestamp(root["created_at"], label="J2-off diagnostic creation")
    action = _action(context, 1)
    exact = {
        "schema_version": SCHEMA_VERSION,
        "kind": J2_OFF_DIAGNOSTIC_KIND,
        "release": _release_reference(context),
        "firmware_binary": context.release_root["firmware"]["binary"],
        "action": _action_reference(context, 1),
        "j2_driver_power_confirmed_off": True,
        "formal_u07_claim_absence": _formal_u07_snapshot(context),
        "network": {"get_requests": 4, "post_requests": 0},
        "claim_created": False,
        "visible_refresh_authorized": False,
        "firmware_upload_performed_by_this_tool": False,
        "state": "j2_off_same_boot_four_get_diagnostic_pass",
    }
    for key, wanted in exact.items():
        if root[key] != wanted:
            raise ColorLabPhysicalError(f"J2-off diagnostic {key} differs")
    registry = _resolved_registry(claim_registry, create=False)
    _assert_absent(
        _claim_path(registry, str(action["action_id"])),
        label="ordinal 1 claim",
    )
    snapshot = root["snapshot"]
    preflight_value = Preflight(
        snapshot["version"],
        snapshot["manifest"],
        snapshot["status"],
        snapshot["report"],
        snapshot["boot_nonce"],
    )
    _validate_version(preflight_value.version)
    _validate_manifest(preflight_value.manifest, context.actions)
    _validate_status(
        preflight_value.status,
        action=action,
        phase="ready",
        expected_busy=0,
    )
    _validate_preflight_report(
        preflight_value.report,
        action=action,
        boot_nonce=preflight_value.boot_nonce,
    )
    if root["boot_nonce"] != preflight_value.boot_nonce:
        raise ColorLabPhysicalError("J2-off diagnostic boot nonce differs")
    transcript = root["transcript"]
    if (
        not isinstance(transcript, list)
        or len(transcript) != 4
        or [item.get("method") for item in transcript] != ["GET"] * 4
        or [item.get("path") for item in transcript]
        != [
            campaign.ENDPOINTS[name]
            for name in ("version", "manifest", "status", "report")
        ]
        or [item.get("response") for item in transcript]
        != [
            preflight_value.version,
            preflight_value.manifest,
            preflight_value.status,
            preflight_value.report,
        ]
    ):
        raise ColorLabPhysicalError("J2-off diagnostic transcript differs")
    return dict(root)


def _file_reference(path: Path, *, label: str) -> dict[str, Any]:
    payload = _read(path, label=label)
    root = _decode(payload, label=label)
    digest = _validate_seal(root, label=label)
    return {
        "file": str(Path(path).resolve()),
        "bytes": len(payload),
        "file_sha256": campaign.sha256(payload),
        "integrity_sha256": digest,
    }


def _prior_gate(
    context: ReleaseContext,
    ordinal: int,
    *,
    prior_result_file: Path | None,
    prior_observation_file: Path | None,
    claim_registry: Path,
    confirm_no_intervening_visible_refresh: bool,
    j2_off_diagnostic_file: Path | None,
) -> dict[str, Any]:
    if not confirm_no_intervening_visible_refresh:
        raise ColorLabPhysicalError(
            f"ordinal {ordinal} requires live no-intervening-visible-refresh confirmation"
        )
    if ordinal == 1:
        if prior_result_file is not None or prior_observation_file is not None:
            raise ColorLabPhysicalError(
                "ordinal 1 must not receive COLOR_LAB prior files"
            )
        if j2_off_diagnostic_file is None:
            raise ColorLabPhysicalError(
                "ordinal 1 requires the same-boot J2-off diagnostic evidence"
            )
        diagnostic = validate_j2_off_diagnostic(
            context,
            j2_off_diagnostic_file,
            claim_registry=claim_registry,
        )
        predecessor = context.release_root["predecessor_binding"]
        return {
            "kind": "completed_u04_u05_compare_result_claim_and_blind_observation",
            "predecessor_action_id": campaign.FIRST_PREDECESSOR_ACTION_ID,
            "compare_binding_sha256": campaign.sha256(predecessor["compare_binding"]),
            "latest_visible_state": "u04_u05_compare_four_blue_patches",
            "ordinal_1_compiled_white_establishes_clean_baseline": True,
            "j2_off_diagnostic": _file_reference(
                j2_off_diagnostic_file, label="J2-off diagnostic evidence"
            ),
            "required_same_boot_nonce": diagnostic["boot_nonce"],
            "live_no_intervening_visible_refresh_confirmed": True,
        }
    if j2_off_diagnostic_file is not None:
        raise ColorLabPhysicalError(
            "J2-off diagnostic evidence is accepted only for ordinal 1"
        )
    if prior_result_file is None or prior_observation_file is None:
        raise ColorLabPhysicalError(
            f"ordinal {ordinal} requires result and observation for ordinal {ordinal - 1}"
        )
    prior_result = validate_result(
        context,
        prior_result_file,
        claim_registry=claim_registry,
    )
    if (
        prior_result["ordinal"] != ordinal - 1
        or prior_result["outcome"] != "complete_pass"
    ):
        raise ColorLabPhysicalError(
            "prior result is not the exact previous complete action"
        )
    prior_observation = validate_observation(
        context,
        prior_observation_file,
        result_file=prior_result_file,
        claim_registry=claim_registry,
    )
    if (
        prior_observation["ordinal"] != ordinal - 1
        or prior_observation["sequence_gate_pass"] is not True
    ):
        raise ColorLabPhysicalError("prior observation does not unlock the next action")
    return {
        "kind": "exact_previous_color_lab_result_and_observation",
        "prior_ordinal": ordinal - 1,
        "result": _file_reference(prior_result_file, label="prior COLOR_LAB result"),
        "observation": _file_reference(
            prior_observation_file, label="prior COLOR_LAB observation"
        ),
        "required_same_boot_nonce": prior_result["preflight"]["boot_nonce"],
        "live_no_intervening_visible_refresh_confirmed": True,
    }


def _mutation_headers(
    action: Mapping[str, Any],
    *,
    boot_nonce: str,
    intent: str,
    arm_nonce: str | None = None,
) -> dict[str, str]:
    headers = {
        "X-EC5-Build-Tag": contract.BUILD_TAG,
        "X-EC5-Test-Id": contract.TEST_ID,
        "X-EC5-Campaign-Id": contract.CAMPAIGN_ID,
        "X-EC5-Action-Id": str(action["action_id"]),
        "X-EC5-Ordinal": str(action["ordinal"]),
        "X-EC5-Descriptor-Id": str(action["descriptor_id"]),
        "X-EC5-Boot-Nonce": boot_nonce,
        "X-EC5-Intent": intent,
    }
    if arm_nonce is not None:
        headers["X-EC5-Arm-Nonce"] = arm_nonce
    return headers


def _validate_arm_response(
    value: Any, *, action: Mapping[str, Any], boot_nonce: str
) -> str:
    root = _response_identity(value, label="ARM response")
    _exact_keys(
        root,
        {
            "accepted",
            "armed",
            "build_tag",
            "test_id",
            "campaign_id",
            "device_api_version",
            "identity_revision",
            "contract_id",
            "classification",
            "ordinal",
            "descriptor_id",
            "action_id",
            "role",
            "round",
            "branch",
            "boot_nonce",
            "arm_nonce",
            "phase",
            "phase_name",
            "not_hardware_authorization",
        },
        label="ARM response",
    )
    expected = {
        "accepted": True,
        "armed": True,
        "ordinal": action["ordinal"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "round": action["round"],
        "branch": action["branch"],
        "boot_nonce": boot_nonce,
        "phase": 1,
        "phase_name": "ARMED",
        "not_hardware_authorization": True,
    }
    for key, wanted in expected.items():
        if root.get(key) != wanted:
            raise ColorLabPhysicalError(f"ARM response {key} differs")
    return _nonce(root.get("arm_nonce"), label="ARM nonce")


def _validate_execute_response(
    value: Any, *, action: Mapping[str, Any], boot_nonce: str
) -> Mapping[str, Any]:
    root = _response_identity(value, label="EXECUTE response")
    _exact_keys(
        root,
        {
            "accepted",
            "job_id",
            "build_tag",
            "test_id",
            "campaign_id",
            "device_api_version",
            "identity_revision",
            "contract_id",
            "classification",
            "ordinal",
            "descriptor_id",
            "action_id",
            "role",
            "round",
            "branch",
            "boot_nonce",
            "execute_consumed",
            "phase",
            "phase_name",
            "no_retry",
            "no_recovery",
        },
        label="EXECUTE response",
    )
    expected = {
        "accepted": True,
        "job_id": action["ordinal"],
        "ordinal": action["ordinal"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "round": action["round"],
        "branch": action["branch"],
        "boot_nonce": boot_nonce,
        "execute_consumed": True,
        "phase": 2,
        "phase_name": "CONSUMED",
        "no_retry": True,
        "no_recovery": True,
    }
    for key, wanted in expected.items():
        if root.get(key) != wanted:
            raise ColorLabPhysicalError(f"EXECUTE response {key} differs")
    return root


def _validate_terminal_report(
    value: Any, *, action: Mapping[str, Any], boot_nonce: str
) -> Mapping[str, Any]:
    root = _identity(
        value, kind=f"{DEVICE_KIND_PREFIX}-report", label="terminal report"
    )
    exact = {
        "valid": True,
        "boot_nonce": boot_nonce,
        "ordinal": action["ordinal"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "round": action["round"],
        "branch": action["branch"],
        "job_id": action["ordinal"],
        "terminal_state": "COMPLETE",
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": action["ordinal"],
        "phase": 0,
        "phase_name": "READY",
        "next_ordinal": action["ordinal"] + 1,
        "campaign_complete": action["ordinal"] == campaign.ACTION_COUNT,
        "no_retry": True,
        "no_recovery": True,
    }
    for key, wanted in exact.items():
        if root.get(key) != wanted:
            raise ColorLabPhysicalError(f"terminal report {key} differs")
    queued = root.get("job_queued_at_ms")
    started = root.get("job_started_at_ms")
    finished = root.get("job_finished_at_ms")
    if (
        not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (queued, started, finished)
        )
        or not queued <= started <= finished
    ):
        raise ColorLabPhysicalError("terminal report timestamps differ")
    driver = _keys(
        root.get("driver"),
        {
            "driver_evidence_schema_version",
            "valid",
            "running",
            "sequence_ok",
            "mapping_applied",
            "input_fnv1a",
            "cs1_dtm_fnv1a",
            "cs2_dtm_fnv1a",
            "safe_finish",
        },
        label="terminal driver evidence",
    )
    frame = action["frame"]["frame"]
    if (
        driver["driver_evidence_schema_version"]
        != contract.DRIVER_EVIDENCE_SCHEMA_VERSION
        or driver["valid"] is not True
        or driver["running"] is not False
        or driver["sequence_ok"] is not True
        or driver["mapping_applied"] is not True
        or driver["input_fnv1a"] != int(frame["fnv1a"], 16)
        or driver["cs1_dtm_fnv1a"] != int(frame["controllers"][0]["fnv1a"], 16)
        or driver["cs2_dtm_fnv1a"] != int(frame["controllers"][1]["fnv1a"], 16)
    ):
        raise ColorLabPhysicalError("terminal driver identity differs")
    safe = _keys(
        driver["safe_finish"],
        {"busy_before_pins_low", "busy_after_pins_low", "busy_after_5ms", "final_gpio"},
        label="terminal driver safe finish",
    )
    if any(
        safe[key] != 1
        for key in ("busy_before_pins_low", "busy_after_pins_low", "busy_after_5ms")
    ):
        raise ColorLabPhysicalError("terminal driver BUSY did not finish idle-high")
    if safe["final_gpio"] != {"busy": 1, "rst": 0, "cs": 0, "cs2": 0}:
        raise ColorLabPhysicalError("terminal driver final GPIO differs")
    return root


def _create_claim(
    context: ReleaseContext,
    *,
    registry: Path,
    action: Mapping[str, Any],
    attempt_id: str,
    authorization: str,
    prior_gate: Mapping[str, Any],
    preflight_value: Preflight,
    formal_u07_snapshot: Mapping[str, Any],
) -> tuple[dict[str, Any], bytes, Path]:
    resolved = _resolved_registry(registry, create=True)
    path = _claim_path(resolved, str(action["action_id"]))
    _assert_absent(path, label="COLOR_LAB action claim")
    claim = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": CLAIM_KIND,
            "registry_id": CLAIM_REGISTRY_ID,
            "created_at": _now(),
            "attempt_id": attempt_id,
            "release": _release_reference(context),
            "action": _action_reference(context, int(action["ordinal"])),
            "authorization_confirmation_sha256": campaign.sha256(
                authorization.encode()
            ),
            "prior_gate": deepcopy(dict(prior_gate)),
            "preflight_sha256": campaign.sha256(preflight_value.as_dict()),
            "boot_nonce": preflight_value.boot_nonce,
            "formal_u07_claim_absence_before_first_post": deepcopy(
                dict(formal_u07_snapshot)
            ),
            "state": "permanently_claimed_before_first_arm_post",
            "maximum_arm_posts": 1,
            "maximum_execute_posts": 1,
            "automatic_chaining": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        }
    )
    payload = _write_new(path, claim)
    return claim, payload, path


def run_once(
    context: ReleaseContext,
    base_url: str,
    ordinal: int,
    *,
    authorization: str,
    result_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    prior_result_file: Path | None = None,
    prior_observation_file: Path | None = None,
    j2_off_diagnostic_file: Path | None = None,
    confirm_no_intervening_visible_refresh: bool,
    confirm_j2_on: bool,
    confirm_electrical_normal: bool,
    temperature_c: float,
    requester: Requester = http_request,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    poll_count: int = DEFAULT_POLL_COUNT,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Consume only one ordinal; no code path invokes the next action."""

    _revalidate_real_release(context)
    action = _action(context, ordinal)
    if authorization != required_authorization(context, ordinal):
        raise ColorLabPhysicalError("exact per-action authorization is required")
    if not confirm_j2_on or not confirm_electrical_normal:
        raise ColorLabPhysicalError("live J2-on electrical confirmation is required")
    if (
        isinstance(temperature_c, bool)
        or not isinstance(temperature_c, (int, float))
        or not math.isfinite(float(temperature_c))
        or not MIN_TEMPERATURE_C <= temperature_c <= MAX_TEMPERATURE_C
    ):
        raise ColorLabPhysicalError("temperature is outside 10..45 C")
    if (
        isinstance(poll_count, bool)
        or not isinstance(poll_count, int)
        or poll_count < 1
    ):
        raise ColorLabPhysicalError("poll count is invalid")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(float(timeout))
        or timeout <= 0
        or isinstance(poll_interval_seconds, bool)
        or not isinstance(poll_interval_seconds, (int, float))
        or not math.isfinite(float(poll_interval_seconds))
        or poll_interval_seconds < 0
    ):
        raise ColorLabPhysicalError("timeout/poll interval is invalid")
    result_target, registry = _validate_execution_paths(
        result_file=Path(result_file),
        claim_registry=claim_registry,
        action_id=str(action["action_id"]),
    )
    prior_gate = _prior_gate(
        context,
        ordinal,
        prior_result_file=prior_result_file,
        prior_observation_file=prior_observation_file,
        claim_registry=registry,
        confirm_no_intervening_visible_refresh=confirm_no_intervening_visible_refresh,
        j2_off_diagnostic_file=j2_off_diagnostic_file,
    )
    formal_before = _formal_u07_snapshot(context)
    audited = _AuditRequester(requester)
    preflight_value = _fresh_preflight(
        context, base_url, ordinal, audited, timeout=timeout
    )
    if len(audited.records) != 4:
        raise ColorLabPhysicalError("fresh preflight request count differs")
    if prior_gate.get("required_same_boot_nonce") != preflight_value.boot_nonce:
        raise ColorLabPhysicalError(
            "current device boot nonce differs from the exact previous action"
        )
    attempt_id = str(uuid.uuid4())
    claim, claim_payload, claim_path = _create_claim(
        context,
        registry=registry,
        action=action,
        attempt_id=attempt_id,
        authorization=authorization,
        prior_gate=prior_gate,
        preflight_value=preflight_value,
        formal_u07_snapshot=formal_before,
    )
    started_at = _now()
    origin = _base_url(base_url)
    outcome = "unknown_do_not_retry_or_recover"
    error_text: str | None = None
    device: dict[str, Any] = {
        "arm_response": None,
        "armed_status": None,
        "execute_response": None,
        "terminal_status": None,
        "terminal_report": None,
    }
    try:
        arm_raw = audited(
            origin,
            campaign.ENDPOINTS["arm"],
            method="POST",
            headers=_mutation_headers(
                action,
                boot_nonce=preflight_value.boot_nonce,
                intent=campaign.ARM_INTENT,
            ),
            timeout=timeout,
        )[1]
        device["arm_response"] = deepcopy(dict(arm_raw))
        arm_nonce = _validate_arm_response(
            arm_raw, action=action, boot_nonce=preflight_value.boot_nonce
        )
        armed_raw = audited(
            origin,
            campaign.ENDPOINTS["status"],
            method="GET",
            headers=None,
            timeout=timeout,
        )[1]
        device["armed_status"] = deepcopy(dict(armed_raw))
        _validate_status(
            armed_raw,
            action=action,
            phase="armed",
            boot_nonce=preflight_value.boot_nonce,
        )
        execute_raw = audited(
            origin,
            campaign.ENDPOINTS["execute"],
            method="POST",
            headers=_mutation_headers(
                action,
                boot_nonce=preflight_value.boot_nonce,
                arm_nonce=arm_nonce,
                intent=campaign.EXECUTE_INTENT,
            ),
            timeout=timeout,
        )[1]
        device["execute_response"] = deepcopy(dict(execute_raw))
        _validate_execute_response(
            execute_raw, action=action, boot_nonce=preflight_value.boot_nonce
        )
        terminal: Mapping[str, Any] | None = None
        terminal_status_response_seen = False
        last_terminal_get_error: Exception | None = None
        for _index in range(poll_count):
            records_before_get = len(audited.records)
            try:
                status_raw = audited(
                    origin,
                    campaign.ENDPOINTS["status"],
                    method="GET",
                    headers=None,
                    timeout=timeout,
                )[1]
            except Exception as error:
                # The synchronous display operation can temporarily prevent the
                # ESP32 HTTP server from answering.  A status GET is read-only,
                # so bounded polling may continue; ARM and EXECUTE are never
                # issued again.  If a response was recorded before the error
                # (for example an HTTP error), retain the existing fail-closed
                # behavior instead of hiding transcripted evidence.
                if len(audited.records) != records_before_get:
                    raise
                last_terminal_get_error = error
            else:
                terminal_status_response_seen = True
                if (
                    status_raw.get("phase") == 0
                    and status_raw.get("next_ordinal") == ordinal + 1
                ):
                    terminal = _validate_status(
                        status_raw,
                        action=action,
                        phase="terminal",
                        boot_nonce=preflight_value.boot_nonce,
                    )
                    break
                if status_raw.get("state") in ("fault", "fault_locked"):
                    raise ColorLabPhysicalError("device entered persistent fault")
            if _index + 1 < poll_count:
                sleeper(poll_interval_seconds)
        if terminal is None:
            if (
                not terminal_status_response_seen
                and last_terminal_get_error is not None
            ):
                raise last_terminal_get_error
            raise ColorLabPhysicalError("device did not reach terminal state")
        device["terminal_status"] = deepcopy(dict(terminal))
        report_raw = audited(
            origin,
            campaign.ENDPOINTS["report"],
            method="GET",
            headers=None,
            timeout=timeout,
        )[1]
        device["terminal_report"] = deepcopy(dict(report_raw))
        _validate_terminal_report(
            report_raw, action=action, boot_nonce=preflight_value.boot_nonce
        )
        if audited.arm_posts != 1 or audited.execute_posts != 1:
            raise ColorLabPhysicalError("mutation count differs from one ARM/EXECUTE")
        outcome = "complete_pass"
    except Exception as error:  # permanent claim forbids retry/recovery
        error_text = str(error)
    try:
        formal_after = _formal_u07_snapshot(context)
    except ColorLabPhysicalError as error:
        formal_after = {
            "snapshot_failed": True,
            "error": str(error),
        }
        outcome = "unknown_do_not_retry_or_recover"
        error_text = f"formal U07 post-action snapshot failed: {error}"
    if formal_after != formal_before:
        outcome = "unknown_do_not_retry_or_recover"
        error_text = "formal U07 claim registry changed during action"
    result = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": RESULT_KIND,
            "release": _release_reference(context),
            "ordinal": ordinal,
            "action": _action_reference(context, ordinal),
            "attempt_id": attempt_id,
            "claim": {
                "file": str(claim_path),
                "bytes": len(claim_payload),
                "file_sha256": campaign.sha256(claim_payload),
                "integrity_sha256": claim["integrity"]["canonical_sha256"],
                "state": claim["state"],
            },
            "prior_gate": prior_gate,
            "preflight": preflight_value.as_dict(),
            "authorization_confirmation_sha256": campaign.sha256(
                authorization.encode()
            ),
            "operator_pre_action": {
                "j2_on": True,
                "electrical_normal": True,
                "temperature_c": float(temperature_c),
            },
            "formal_u07_claim_absence_before_action": formal_before,
            "formal_u07_claim_absence_after_action": formal_after,
            "started_at": started_at,
            "completed_at": _now(),
            "outcome": outcome,
            "error": error_text,
            "network": {
                "get_requests": sum(
                    item["method"] == "GET" for item in audited.records
                ),
                "arm_posts": audited.arm_posts,
                "execute_posts": audited.execute_posts,
                "maximum_arm_posts": 1,
                "maximum_execute_posts": 1,
                "automatic_retry": False,
                "automatic_recovery": False,
                "automatic_chaining": False,
            },
            "transcript": audited.records,
            "device": device,
            "state": "authorization_permanently_consumed_do_not_rerun",
        }
    )
    _write_new(result_target, result)
    return result


def _validate_claim(
    context: ReleaseContext,
    root: Mapping[str, Any],
    *,
    claim_registry: Path,
    started_at: datetime,
) -> Mapping[str, Any]:
    action = _action(context, int(root["ordinal"]))
    registry = _resolved_registry(claim_registry, create=False)
    path = _claim_path(registry, str(action["action_id"]))
    payload = _read(path, label="COLOR_LAB permanent claim")
    claim = _decode(payload, label="COLOR_LAB permanent claim")
    _validate_seal(claim, label="COLOR_LAB permanent claim")
    expected_ref = {
        "file": str(path),
        "bytes": len(payload),
        "file_sha256": campaign.sha256(payload),
        "integrity_sha256": claim["integrity"]["canonical_sha256"],
        "state": "permanently_claimed_before_first_arm_post",
    }
    if root["claim"] != expected_ref:
        raise ColorLabPhysicalError("result claim reference differs")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "attempt_id": root["attempt_id"],
        "release": _release_reference(context),
        "action": _action_reference(context, int(root["ordinal"])),
        "authorization_confirmation_sha256": root["authorization_confirmation_sha256"],
        "prior_gate": root["prior_gate"],
        "preflight_sha256": campaign.sha256(root["preflight"]),
        "boot_nonce": root["preflight"]["boot_nonce"],
        "formal_u07_claim_absence_before_first_post": root[
            "formal_u07_claim_absence_before_action"
        ],
        "state": "permanently_claimed_before_first_arm_post",
        "maximum_arm_posts": 1,
        "maximum_execute_posts": 1,
        "automatic_chaining": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }
    _exact_keys(claim, set(expected) | {"created_at", "integrity"}, label="claim")
    for key, wanted in expected.items():
        if claim[key] != wanted:
            raise ColorLabPhysicalError(f"claim {key} differs")
    if _timestamp(claim["created_at"], label="claim creation") > started_at:
        raise ColorLabPhysicalError("claim was not created before execution")
    return claim


def _validate_transcript(context: ReleaseContext, root: Mapping[str, Any]) -> None:
    transcript = root["transcript"]
    if not isinstance(transcript, list) or len(transcript) < 9:
        raise ColorLabPhysicalError("result transcript is incomplete")
    preflight_paths = [
        campaign.ENDPOINTS[name] for name in ("version", "manifest", "status", "report")
    ]
    if [item.get("path") for item in transcript[:4]] != preflight_paths or any(
        item.get("method") != "GET" for item in transcript[:4]
    ):
        raise ColorLabPhysicalError("result preflight transcript differs")
    posts = [item for item in transcript if item.get("method") == "POST"]
    if [item.get("path") for item in posts] != [
        campaign.ENDPOINTS["arm"],
        campaign.ENDPOINTS["execute"],
    ]:
        raise ColorLabPhysicalError("result mutation transcript differs")
    action = _action(context, int(root["ordinal"]))
    preflight_value = Preflight(
        root["preflight"]["version"],
        root["preflight"]["manifest"],
        root["preflight"]["status"],
        root["preflight"]["report"],
        root["preflight"]["boot_nonce"],
    )
    _validate_version(preflight_value.version)
    _validate_manifest(preflight_value.manifest, context.actions)
    _validate_status(preflight_value.status, action=action, phase="ready")
    _validate_preflight_report(
        preflight_value.report,
        action=action,
        boot_nonce=preflight_value.boot_nonce,
    )
    if [item["response"] for item in transcript[:4]] != [
        preflight_value.version,
        preflight_value.manifest,
        preflight_value.status,
        preflight_value.report,
    ]:
        raise ColorLabPhysicalError("stored preflight differs from transcript")
    if root["outcome"] == "complete_pass":
        device = root["device"]
        arm_nonce = _validate_arm_response(
            device["arm_response"],
            action=action,
            boot_nonce=preflight_value.boot_nonce,
        )
        _validate_status(
            device["armed_status"],
            action=action,
            phase="armed",
            boot_nonce=preflight_value.boot_nonce,
        )
        _validate_execute_response(
            device["execute_response"],
            action=action,
            boot_nonce=preflight_value.boot_nonce,
        )
        _validate_status(
            device["terminal_status"],
            action=action,
            phase="terminal",
            boot_nonce=preflight_value.boot_nonce,
        )
        _validate_terminal_report(
            device["terminal_report"],
            action=action,
            boot_nonce=preflight_value.boot_nonce,
        )
        if (
            not any(
                item["response"] == device["terminal_status"] for item in transcript
            )
            or transcript[-1]["response"] != device["terminal_report"]
        ):
            raise ColorLabPhysicalError("terminal evidence differs from transcript")
        execute_headers = _mutation_headers(
            action,
            boot_nonce=preflight_value.boot_nonce,
            arm_nonce=arm_nonce,
            intent=campaign.EXECUTE_INTENT,
        )
        if (
            posts[0]["headers"]
            != _mutation_headers(
                action,
                boot_nonce=preflight_value.boot_nonce,
                intent=campaign.ARM_INTENT,
            )
            or posts[1]["headers"] != execute_headers
        ):
            raise ColorLabPhysicalError("mutation headers differ")


def _validate_late_terminal_source(
    context: ReleaseContext, root: Mapping[str, Any]
) -> None:
    """Accept only the narrow first-terminal-status-timeout source shape."""

    if root.get("outcome") != "unknown_do_not_retry_or_recover":
        raise ColorLabPhysicalError(
            "reconciliation source is not an unknown consumed result"
        )
    action = _action(context, int(root["ordinal"]))
    error = root.get("error")
    expected_error_prefix = f"GET {campaign.ENDPOINTS['status']} failed:"
    if not isinstance(error, str) or not error.startswith(expected_error_prefix):
        raise ColorLabPhysicalError(
            "reconciliation source is not the first terminal status GET failure"
        )
    network = root["network"]
    if (
        network["get_requests"] != 5
        or network["arm_posts"] != 1
        or network["execute_posts"] != 1
    ):
        raise ColorLabPhysicalError(
            "reconciliation source request counts differ from the late-timeout case"
        )
    transcript = root["transcript"]
    expected_paths = [
        campaign.ENDPOINTS["version"],
        campaign.ENDPOINTS["manifest"],
        campaign.ENDPOINTS["status"],
        campaign.ENDPOINTS["report"],
        campaign.ENDPOINTS["arm"],
        campaign.ENDPOINTS["status"],
        campaign.ENDPOINTS["execute"],
    ]
    expected_methods = ["GET", "GET", "GET", "GET", "POST", "GET", "POST"]
    expected_statuses = [200, 200, 200, 200, 201, 200, 202]
    if (
        not isinstance(transcript, list)
        or len(transcript) != len(expected_paths)
        or [item.get("path") for item in transcript] != expected_paths
        or [item.get("method") for item in transcript] != expected_methods
        or [item.get("status") for item in transcript] != expected_statuses
        or any(
            not isinstance(item, Mapping)
            or set(item) != {"method", "path", "headers", "status", "response"}
            or not isinstance(item["status"], int)
            or isinstance(item["status"], bool)
            or not 200 <= item["status"] < 300
            for item in transcript
        )
    ):
        raise ColorLabPhysicalError(
            "reconciliation source transcript is not the exact late-timeout prefix"
        )

    preflight_root = root["preflight"]
    preflight_value = Preflight(
        preflight_root["version"],
        preflight_root["manifest"],
        preflight_root["status"],
        preflight_root["report"],
        preflight_root["boot_nonce"],
    )
    _validate_version(preflight_value.version)
    _validate_manifest(preflight_value.manifest, context.actions)
    _validate_status(preflight_value.status, action=action, phase="ready")
    _validate_preflight_report(
        preflight_value.report,
        action=action,
        boot_nonce=preflight_value.boot_nonce,
    )
    if [item["response"] for item in transcript[:4]] != [
        preflight_value.version,
        preflight_value.manifest,
        preflight_value.status,
        preflight_value.report,
    ]:
        raise ColorLabPhysicalError("reconciliation source preflight differs")

    device = _exact_keys(
        root["device"],
        {
            "arm_response",
            "armed_status",
            "execute_response",
            "terminal_status",
            "terminal_report",
        },
        label="reconciliation source device evidence",
    )
    boot_nonce = preflight_value.boot_nonce
    arm_nonce = _validate_arm_response(
        device["arm_response"], action=action, boot_nonce=boot_nonce
    )
    _validate_status(
        device["armed_status"],
        action=action,
        phase="armed",
        boot_nonce=boot_nonce,
    )
    _validate_execute_response(
        device["execute_response"], action=action, boot_nonce=boot_nonce
    )
    if device["terminal_status"] is not None or device["terminal_report"] is not None:
        raise ColorLabPhysicalError(
            "reconciliation source already contains terminal evidence"
        )
    if [item["response"] for item in transcript[4:]] != [
        device["arm_response"],
        device["armed_status"],
        device["execute_response"],
    ]:
        raise ColorLabPhysicalError("reconciliation source mutation evidence differs")
    if (
        transcript[4]["headers"]
        != _mutation_headers(action, boot_nonce=boot_nonce, intent=campaign.ARM_INTENT)
        or transcript[6]["headers"]
        != _mutation_headers(
            action,
            boot_nonce=boot_nonce,
            arm_nonce=arm_nonce,
            intent=campaign.EXECUTE_INTENT,
        )
        or any(transcript[index]["headers"] != {} for index in (0, 1, 2, 3, 5))
    ):
        raise ColorLabPhysicalError("reconciliation source request headers differ")


def _validate_reconciliation_result(
    context: ReleaseContext,
    root: Mapping[str, Any],
    *,
    result_file: Path,
    claim_registry: Path,
) -> None:
    reconciliation = _exact_keys(
        root["reconciliation"],
        {
            "kind",
            "reconciled_at",
            "source_result",
            "source_outcome",
            "source_error",
            "source_completed_at",
            "source_transcript_sha256",
            "readback",
            "source_result_not_modified",
            "authorization_reused",
            "mutation_requests_sent",
            "automatic_retry",
            "automatic_recovery",
            "integrity",
        },
        label="late-terminal reconciliation",
    )
    _validate_seal(reconciliation, label="late-terminal reconciliation")
    source_ref = _exact_keys(
        reconciliation["source_result"],
        {"file", "bytes", "file_sha256", "integrity_sha256"},
        label="reconciliation source result reference",
    )
    source_path = Path(str(source_ref["file"]))
    if os.path.normcase(str(source_path.resolve())) == os.path.normcase(
        str(Path(result_file).resolve())
    ):
        raise ColorLabPhysicalError("reconciliation result cannot reference itself")
    expected_source_ref = _file_reference(
        source_path, label="late-terminal source result"
    )
    if dict(source_ref) != expected_source_ref:
        raise ColorLabPhysicalError("reconciliation source result reference differs")
    source = validate_result(context, source_path, claim_registry=claim_registry)
    if "reconciliation" in source:
        raise ColorLabPhysicalError("nested result reconciliation is forbidden")
    _validate_late_terminal_source(context, source)

    action = _action(context, int(root["ordinal"]))
    boot_nonce = str(source["preflight"]["boot_nonce"])
    device = root["device"]
    readback = _exact_keys(
        reconciliation["readback"],
        {
            "boot_nonce",
            "get_requests",
            "post_requests",
            "paths",
            "transcript",
            "terminal_status_sha256",
            "terminal_report_sha256",
        },
        label="late-terminal readback",
    )
    readback_transcript = readback["transcript"]
    if (
        not isinstance(readback_transcript, list)
        or len(readback_transcript) != 2
        or [item.get("method") for item in readback_transcript] != ["GET", "GET"]
        or [item.get("path") for item in readback_transcript]
        != [campaign.ENDPOINTS["status"], campaign.ENDPOINTS["report"]]
        or [item.get("status") for item in readback_transcript] != [200, 200]
        or any(item.get("headers") != {} for item in readback_transcript)
        or any(
            not isinstance(item.get("status"), int)
            or isinstance(item.get("status"), bool)
            or not 200 <= item["status"] < 300
            for item in readback_transcript
        )
    ):
        raise ColorLabPhysicalError("late-terminal readback was not exactly two GETs")
    _validate_status(
        device["terminal_status"],
        action=action,
        phase="terminal",
        boot_nonce=boot_nonce,
    )
    _validate_terminal_report(
        device["terminal_report"], action=action, boot_nonce=boot_nonce
    )
    expected_readback = {
        "boot_nonce": boot_nonce,
        "get_requests": 2,
        "post_requests": 0,
        "paths": [campaign.ENDPOINTS["status"], campaign.ENDPOINTS["report"]],
        "transcript": readback_transcript,
        "terminal_status_sha256": campaign.sha256(device["terminal_status"]),
        "terminal_report_sha256": campaign.sha256(device["terminal_report"]),
    }
    if dict(readback) != expected_readback:
        raise ColorLabPhysicalError("late-terminal readback provenance differs")
    if [item["response"] for item in readback_transcript] != [
        device["terminal_status"],
        device["terminal_report"],
    ]:
        raise ColorLabPhysicalError("late-terminal readback responses differ")

    unchanged_fields = {
        "schema_version",
        "kind",
        "release",
        "ordinal",
        "action",
        "attempt_id",
        "claim",
        "prior_gate",
        "preflight",
        "authorization_confirmation_sha256",
        "operator_pre_action",
        "formal_u07_claim_absence_before_action",
        "formal_u07_claim_absence_after_action",
        "started_at",
        "state",
    }
    if any(root[field] != source[field] for field in unchanged_fields):
        raise ColorLabPhysicalError(
            "reconciled result changed immutable source evidence"
        )
    expected_device = deepcopy(dict(source["device"]))
    expected_device["terminal_status"] = deepcopy(dict(device["terminal_status"]))
    expected_device["terminal_report"] = deepcopy(dict(device["terminal_report"]))
    expected_network = deepcopy(dict(source["network"]))
    expected_network["get_requests"] += 2
    if (
        root["device"] != expected_device
        or root["network"] != expected_network
        or root["transcript"] != source["transcript"] + readback_transcript
    ):
        raise ColorLabPhysicalError("reconciled result evidence composition differs")

    reconciled_at = _timestamp(
        reconciliation["reconciled_at"], label="reconciliation time"
    )
    if (
        reconciled_at
        < _timestamp(source["completed_at"], label="source result completion")
        or root["completed_at"] != reconciliation["reconciled_at"]
    ):
        raise ColorLabPhysicalError("reconciliation timestamp differs")
    expected_reconciliation = _seal(
        {
            "kind": RECONCILIATION_KIND,
            "reconciled_at": root["completed_at"],
            "source_result": expected_source_ref,
            "source_outcome": "unknown_do_not_retry_or_recover",
            "source_error": source["error"],
            "source_completed_at": source["completed_at"],
            "source_transcript_sha256": campaign.sha256(
                campaign.canonical_json_bytes(source["transcript"])
            ),
            "readback": expected_readback,
            "source_result_not_modified": True,
            "authorization_reused": False,
            "mutation_requests_sent": 0,
            "automatic_retry": False,
            "automatic_recovery": False,
        }
    )
    if dict(reconciliation) != expected_reconciliation:
        raise ColorLabPhysicalError("late-terminal reconciliation identity differs")


def validate_result(
    context: ReleaseContext,
    result_file: Path,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    _revalidate_real_release(context)
    payload = _read(result_file, label="COLOR_LAB result")
    root = _decode(payload, label="COLOR_LAB result")
    expected_fields = {
        "schema_version",
        "kind",
        "release",
        "ordinal",
        "action",
        "attempt_id",
        "claim",
        "prior_gate",
        "preflight",
        "authorization_confirmation_sha256",
        "operator_pre_action",
        "formal_u07_claim_absence_before_action",
        "formal_u07_claim_absence_after_action",
        "started_at",
        "completed_at",
        "outcome",
        "error",
        "network",
        "transcript",
        "device",
        "state",
        "integrity",
    }
    reconciled = "reconciliation" in root
    if reconciled:
        expected_fields.add("reconciliation")
    _exact_keys(root, expected_fields, label="COLOR_LAB result")
    _validate_seal(root, label="COLOR_LAB result")
    ordinal = root["ordinal"]
    _action(context, ordinal)
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != RESULT_KIND
        or root["release"] != _release_reference(context)
        or root["action"] != _action_reference(context, ordinal)
        or root["authorization_confirmation_sha256"]
        != campaign.sha256(required_authorization(context, ordinal).encode())
        or root["state"] != "authorization_permanently_consumed_do_not_rerun"
    ):
        raise ColorLabPhysicalError("COLOR_LAB result identity differs")
    started = _timestamp(root["started_at"], label="result start")
    completed = _timestamp(root["completed_at"], label="result completion")
    if completed < started:
        raise ColorLabPhysicalError("result timestamps are reversed")
    _validate_claim(context, root, claim_registry=claim_registry, started_at=started)
    network = _exact_keys(
        root["network"],
        {
            "get_requests",
            "arm_posts",
            "execute_posts",
            "maximum_arm_posts",
            "maximum_execute_posts",
            "automatic_retry",
            "automatic_recovery",
            "automatic_chaining",
        },
        label="result network",
    )
    transcript = root["transcript"]
    if not isinstance(transcript, list):
        raise ColorLabPhysicalError("result transcript is malformed")
    post_paths = [
        item.get("path") for item in transcript if item.get("method") == "POST"
    ]
    if (
        network["get_requests"]
        != sum(item.get("method") == "GET" for item in transcript)
        or network["arm_posts"]
        != sum(
            item.get("method") == "POST"
            and item.get("path") == campaign.ENDPOINTS["arm"]
            for item in transcript
        )
        or network["execute_posts"]
        != sum(
            item.get("method") == "POST"
            and item.get("path") == campaign.ENDPOINTS["execute"]
            for item in transcript
        )
        or network["maximum_arm_posts"] != 1
        or network["maximum_execute_posts"] != 1
        or network["arm_posts"] not in (0, 1)
        or network["execute_posts"] not in (0, 1)
        or post_paths
        not in (
            [],
            [campaign.ENDPOINTS["arm"]],
            [campaign.ENDPOINTS["arm"], campaign.ENDPOINTS["execute"]],
        )
        or any(
            network[key] is not False
            for key in ("automatic_retry", "automatic_recovery", "automatic_chaining")
        )
    ):
        raise ColorLabPhysicalError("result network evidence differs")
    operator = _exact_keys(
        root["operator_pre_action"],
        {"j2_on", "electrical_normal", "temperature_c"},
        label="result operator pre-action",
    )
    if (
        operator["j2_on"] is not True
        or operator["electrical_normal"] is not True
        or isinstance(operator["temperature_c"], bool)
        or not isinstance(operator["temperature_c"], (int, float))
        or not math.isfinite(float(operator["temperature_c"]))
        or not MIN_TEMPERATURE_C
        <= float(operator["temperature_c"])
        <= MAX_TEMPERATURE_C
    ):
        raise ColorLabPhysicalError("result operator pre-action differs")
    if root["outcome"] == "complete_pass":
        if (
            root["error"] is not None
            or network["arm_posts"] != 1
            or network["execute_posts"] != 1
            or root["formal_u07_claim_absence_before_action"]
            != root["formal_u07_claim_absence_after_action"]
        ):
            raise ColorLabPhysicalError("complete result boundary differs")
        _validate_transcript(context, root)
        if reconciled:
            _validate_reconciliation_result(
                context,
                root,
                result_file=result_file,
                claim_registry=claim_registry,
            )
    elif root["outcome"] != "unknown_do_not_retry_or_recover":
        raise ColorLabPhysicalError("result outcome differs")
    elif reconciled:
        raise ColorLabPhysicalError("unknown result cannot contain reconciliation")
    return dict(root)


def reconcile_result(
    context: ReleaseContext,
    base_url: str,
    *,
    source_result_file: Path,
    result_file: Path,
    reconciliation_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    requester: Requester = http_request,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Seal a completed result from two late terminal GETs; never send a POST."""

    _revalidate_real_release(context)
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(float(timeout))
        or timeout <= 0
    ):
        raise ColorLabPhysicalError("reconciliation timeout is invalid")
    target = _new_output_target(result_file, label="reconciled COLOR_LAB result")
    evidence_target = _new_output_target(
        reconciliation_file, label="late-terminal reconciliation evidence"
    )
    if os.path.normcase(str(target)) == os.path.normcase(str(evidence_target)):
        raise ColorLabPhysicalError(
            "reconciled result and reconciliation evidence paths must differ"
        )
    source_path = Path(source_result_file)
    source = validate_result(context, source_path, claim_registry=claim_registry)
    _validate_late_terminal_source(context, source)
    formal = _formal_u07_snapshot(context)
    if (
        source["formal_u07_claim_absence_before_action"] != formal
        or source["formal_u07_claim_absence_after_action"] != formal
    ):
        raise ColorLabPhysicalError(
            "formal U07 boundary changed before late-terminal reconciliation"
        )

    action = _action(context, int(source["ordinal"]))
    boot_nonce = str(source["preflight"]["boot_nonce"])
    origin = _base_url(base_url)
    audited = _AuditRequester(requester)
    status_raw = audited(
        origin,
        campaign.ENDPOINTS["status"],
        method="GET",
        headers=None,
        timeout=float(timeout),
    )[1]
    terminal_status = _validate_status(
        status_raw,
        action=action,
        phase="terminal",
        boot_nonce=boot_nonce,
    )
    report_raw = audited(
        origin,
        campaign.ENDPOINTS["report"],
        method="GET",
        headers=None,
        timeout=float(timeout),
    )[1]
    terminal_report = _validate_terminal_report(
        report_raw, action=action, boot_nonce=boot_nonce
    )
    if (
        len(audited.records) != 2
        or [item["method"] for item in audited.records] != ["GET", "GET"]
        or audited.arm_posts != 0
        or audited.execute_posts != 0
    ):
        raise ColorLabPhysicalError(
            "late-terminal reconciliation was not exactly two read-only GETs"
        )
    if _formal_u07_snapshot(context) != formal:
        raise ColorLabPhysicalError(
            "formal U07 boundary changed during late-terminal reconciliation"
        )

    completed_at = _now()
    source_reference = _file_reference(source_path, label="late-terminal source result")
    readback = {
        "boot_nonce": boot_nonce,
        "get_requests": 2,
        "post_requests": 0,
        "paths": [campaign.ENDPOINTS["status"], campaign.ENDPOINTS["report"]],
        "transcript": deepcopy(audited.records),
        "terminal_status_sha256": campaign.sha256(terminal_status),
        "terminal_report_sha256": campaign.sha256(terminal_report),
    }
    unsigned = deepcopy(dict(source))
    unsigned.pop("integrity")
    unsigned["completed_at"] = completed_at
    unsigned["outcome"] = "complete_pass"
    unsigned["error"] = None
    unsigned["network"]["get_requests"] += 2
    unsigned["transcript"] = list(unsigned["transcript"]) + deepcopy(audited.records)
    unsigned["device"]["terminal_status"] = deepcopy(dict(terminal_status))
    unsigned["device"]["terminal_report"] = deepcopy(dict(terminal_report))
    unsigned["reconciliation"] = _seal(
        {
            "kind": RECONCILIATION_KIND,
            "reconciled_at": completed_at,
            "source_result": source_reference,
            "source_outcome": "unknown_do_not_retry_or_recover",
            "source_error": source["error"],
            "source_completed_at": source["completed_at"],
            "source_transcript_sha256": campaign.sha256(
                campaign.canonical_json_bytes(source["transcript"])
            ),
            "readback": readback,
            "source_result_not_modified": True,
            "authorization_reused": False,
            "mutation_requests_sent": 0,
            "automatic_retry": False,
            "automatic_recovery": False,
        }
    )
    result = _seal(unsigned)
    _write_new(target, result)
    result_reference = _file_reference(
        target, label="derived complete COLOR_LAB result"
    )
    evidence = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": RECONCILIATION_KIND,
            "created_at": _now(),
            "release": _release_reference(context),
            "ordinal": source["ordinal"],
            "action": deepcopy(source["action"]),
            "source_result": source_reference,
            "derived_complete_result": result_reference,
            "provenance": deepcopy(result["reconciliation"]),
            "readback_only": True,
            "get_requests": 2,
            "mutation_requests_sent": 0,
            "original_result_mutated": False,
            "automatic_retry": False,
            "automatic_recovery": False,
            "state": "late_terminal_readback_reconciled_without_retry_or_recovery",
        }
    )
    _write_new(evidence_target, evidence)
    return {"result": result, "reconciliation_evidence": evidence}


def validate_reconciliation(
    context: ReleaseContext,
    reconciliation_file: Path,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    """Validate the separately sealed source-to-derived reconciliation chain."""

    _revalidate_real_release(context)
    payload = _read(reconciliation_file, label="late-terminal reconciliation evidence")
    root = _decode(payload, label="late-terminal reconciliation evidence")
    _exact_keys(
        root,
        {
            "schema_version",
            "kind",
            "created_at",
            "release",
            "ordinal",
            "action",
            "source_result",
            "derived_complete_result",
            "provenance",
            "readback_only",
            "get_requests",
            "mutation_requests_sent",
            "original_result_mutated",
            "automatic_retry",
            "automatic_recovery",
            "state",
            "integrity",
        },
        label="late-terminal reconciliation evidence",
    )
    _validate_seal(root, label="late-terminal reconciliation evidence")
    source_ref = _exact_keys(
        root["source_result"],
        {"file", "bytes", "file_sha256", "integrity_sha256"},
        label="reconciliation evidence source reference",
    )
    result_ref = _exact_keys(
        root["derived_complete_result"],
        {"file", "bytes", "file_sha256", "integrity_sha256"},
        label="reconciliation evidence derived reference",
    )
    source_path = Path(str(source_ref["file"]))
    result_path = Path(str(result_ref["file"]))
    if dict(source_ref) != _file_reference(
        source_path, label="late-terminal source result"
    ):
        raise ColorLabPhysicalError("reconciliation evidence source reference differs")
    if dict(result_ref) != _file_reference(
        result_path, label="derived complete COLOR_LAB result"
    ):
        raise ColorLabPhysicalError("reconciliation evidence result reference differs")
    derived = validate_result(context, result_path, claim_registry=claim_registry)
    if derived.get("outcome") != "complete_pass" or "reconciliation" not in derived:
        raise ColorLabPhysicalError(
            "reconciliation evidence does not reference a reconciled complete result"
        )
    ordinal = int(derived["ordinal"])
    exact = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECONCILIATION_KIND,
        "release": _release_reference(context),
        "ordinal": ordinal,
        "action": _action_reference(context, ordinal),
        "source_result": derived["reconciliation"]["source_result"],
        "derived_complete_result": _file_reference(
            result_path, label="derived complete COLOR_LAB result"
        ),
        "provenance": derived["reconciliation"],
        "readback_only": True,
        "get_requests": 2,
        "mutation_requests_sent": 0,
        "original_result_mutated": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "state": "late_terminal_readback_reconciled_without_retry_or_recovery",
    }
    for key, wanted in exact.items():
        if root[key] != wanted:
            raise ColorLabPhysicalError(f"reconciliation evidence {key} differs")
    if _timestamp(root["created_at"], label="reconciliation evidence creation") < (
        _timestamp(derived["completed_at"], label="derived result completion")
    ):
        raise ColorLabPhysicalError("reconciliation evidence predates derived result")
    return dict(root)


def seal_observation(
    context: ReleaseContext,
    *,
    result_file: Path,
    observation_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    operator_report: str,
    temperature_c: float,
    confirm_reference_preview_checked: bool,
    confirm_display_matches_reference: bool,
    confirm_no_unexpected_residual: bool,
    confirm_electrical_normal: bool,
    confirm_esp32_no_restart: bool,
    confirm_clean_white: bool = False,
    confirm_map_fidelity: bool = False,
) -> dict[str, Any]:
    result = validate_result(context, result_file, claim_registry=claim_registry)
    if result["outcome"] != "complete_pass":
        raise ColorLabPhysicalError("observation requires a complete action result")
    if not isinstance(operator_report, str) or not operator_report.strip():
        raise ColorLabPhysicalError("operator report is required")
    if (
        isinstance(temperature_c, bool)
        or not isinstance(temperature_c, (int, float))
        or not math.isfinite(float(temperature_c))
        or not MIN_TEMPERATURE_C <= temperature_c <= MAX_TEMPERATURE_C
    ):
        raise ColorLabPhysicalError("observation temperature is outside 10..45 C")
    confirmations = (
        confirm_reference_preview_checked,
        confirm_display_matches_reference,
        confirm_no_unexpected_residual,
        confirm_electrical_normal,
        confirm_esp32_no_restart,
    )
    if not all(confirmations):
        raise ColorLabPhysicalError("observation requires all common confirmations")
    role = str(result["action"]["role"])
    if _is_white_role(role) and not confirm_clean_white:
        raise ColorLabPhysicalError("white action requires clean-white confirmation")
    if (
        role in (contract.ROLE_U04_PRIMER, contract.ROLE_U07_PRIMER)
        and not confirm_map_fidelity
    ):
        raise ColorLabPhysicalError("primer action requires MAP-fidelity confirmation")
    result_ref = _file_reference(result_file, label="observed COLOR_LAB result")
    observation = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": OBSERVATION_KIND,
            "observed_at": _now(),
            "release": _release_reference(context),
            "ordinal": result["ordinal"],
            "action": deepcopy(result["action"]),
            "result": result_ref,
            "operator_report_verbatim": operator_report.strip(),
            "visual": {
                "reference_preview_checked": True,
                "display_matches_reference": True,
                "no_unexpected_residual": True,
                "full_clean_white": True if _is_white_role(role) else None,
                "map_fidelity_pass": (
                    True
                    if role in (contract.ROLE_U04_PRIMER, contract.ROLE_U07_PRIMER)
                    else None
                ),
            },
            "supervised": {
                "electrical_normal": True,
                "temperature_c": float(temperature_c),
                "esp32_did_not_restart": True,
            },
            "sequence_gate_pass": True,
            "physical_colour_qualification_inferred": False,
            "automatic_next_action_authorized": False,
            "retry_authorized": False,
            "recovery_authorized": False,
        }
    )
    _write_new(observation_file, observation)
    return observation


def validate_observation(
    context: ReleaseContext,
    observation_file: Path,
    *,
    result_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    result = validate_result(context, result_file, claim_registry=claim_registry)
    if result["outcome"] != "complete_pass":
        raise ColorLabPhysicalError("observation result is not complete_pass")
    payload = _read(observation_file, label="COLOR_LAB observation")
    root = _decode(payload, label="COLOR_LAB observation")
    expected_fields = {
        "schema_version",
        "kind",
        "observed_at",
        "release",
        "ordinal",
        "action",
        "result",
        "operator_report_verbatim",
        "visual",
        "supervised",
        "sequence_gate_pass",
        "physical_colour_qualification_inferred",
        "automatic_next_action_authorized",
        "retry_authorized",
        "recovery_authorized",
        "integrity",
    }
    _exact_keys(root, expected_fields, label="COLOR_LAB observation")
    _validate_seal(root, label="COLOR_LAB observation")
    if _timestamp(root["observed_at"], label="observation time") < _timestamp(
        result["completed_at"], label="result completion"
    ):
        raise ColorLabPhysicalError("observation predates result completion")
    role = str(result["action"]["role"])
    expected_visual = {
        "reference_preview_checked": True,
        "display_matches_reference": True,
        "no_unexpected_residual": True,
        "full_clean_white": True if _is_white_role(role) else None,
        "map_fidelity_pass": (
            True
            if role in (contract.ROLE_U04_PRIMER, contract.ROLE_U07_PRIMER)
            else None
        ),
    }
    exact = {
        "schema_version": SCHEMA_VERSION,
        "kind": OBSERVATION_KIND,
        "release": _release_reference(context),
        "ordinal": result["ordinal"],
        "action": result["action"],
        "result": _file_reference(result_file, label="observed COLOR_LAB result"),
        "visual": expected_visual,
        "sequence_gate_pass": True,
        "physical_colour_qualification_inferred": False,
        "automatic_next_action_authorized": False,
        "retry_authorized": False,
        "recovery_authorized": False,
    }
    for key, wanted in exact.items():
        if root[key] != wanted:
            raise ColorLabPhysicalError(f"observation {key} differs")
    supervised = _exact_keys(
        root["supervised"],
        {"electrical_normal", "temperature_c", "esp32_did_not_restart"},
        label="observation supervision",
    )
    if (
        supervised["electrical_normal"] is not True
        or supervised["esp32_did_not_restart"] is not True
        or isinstance(supervised["temperature_c"], bool)
        or not isinstance(supervised["temperature_c"], (int, float))
        or not math.isfinite(float(supervised["temperature_c"]))
        or not MIN_TEMPERATURE_C <= supervised["temperature_c"] <= MAX_TEMPERATURE_C
        or not isinstance(root["operator_report_verbatim"], str)
        or not root["operator_report_verbatim"].strip()
    ):
        raise ColorLabPhysicalError("observation supervision differs")
    return dict(root)


def describe(context: ReleaseContext, ordinal: int) -> dict[str, Any]:
    _action(context, ordinal)
    return {
        "release_execution_eligible": context.execution_eligible,
        "action": _action_reference(context, ordinal),
        "authorization": required_authorization(context, ordinal),
        "requires_prior_result_and_observation": ordinal > 1,
        "white_checkpoint_after_this_action": ordinal
        in campaign.WHITE_CHECKPOINT_ORDINALS,
        "safe_to_pause_after_observation": ordinal
        in campaign.WHITE_CHECKPOINT_ORDINALS,
        "recommended_safe_stop_after_observation": ordinal
        in campaign.RECOMMENDED_SAFE_STOP_ORDINALS,
        "first_complete_u04_u07_round_finished": ordinal
        == campaign.FIRST_FULL_ROUND_STOP_ORDINAL,
        "same_boot_required_to_resume_next_ordinal": ordinal < campaign.ACTION_COUNT,
        "automatic_chaining": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }


def observation_template(context: ReleaseContext, ordinal: int) -> dict[str, Any]:
    """Return the shortest role-specific visual checklist; authorize nothing."""

    action = _action(context, ordinal)
    role = str(action["role"])
    preview_file = PREVIEW_FILES[role]
    preview_payload = _read(preview_file, label=f"{role} monitor preview")
    common = [
        "reference_preview_checked",
        "display_matches_reference_layout",
        "left_right_geometry_consistent",
        "no_unexpected_old_state_residual",
        "electrical_normal",
        "temperature_c_10_to_45",
        "esp32_did_not_restart",
    ]
    if _is_white_role(role):
        role_fields: dict[str, Any] = {
            "full_screen_clean_white": None,
            "residual_or_outline_present": None,
            "residual_location_if_any": "",
        }
    elif role == contract.ROLE_U07_ISOLATED:
        role_fields = {
            "observed_colour_name": "",
            "left_right_patch_same_colour": None,
            "patches_uniform": None,
            "edges_clear_and_even": None,
            "white_background_clean": None,
            "colour_strength_0_to_4": None,
            "optional_hold": {
                "status": "SKIPPED_OR_OBSERVED",
                "minutes_observed": 0,
                "changed_during_hold": None,
                "formal_qualification_inferred": False,
            },
        }
    elif role == contract.ROLE_ATLAS:
        role_fields = {
            "blind_left_visual_equivalence_groups_slots_0_to_7": [],
            "blind_right_visual_equivalence_groups_slots_0_to_7": [],
            "left_right_corresponding_slots_match": None,
            "distinct_visual_group_count": None,
            "decode_only_after_blind_grouping": {
                "left_cs1_slot_codes": list(range(8)),
                "right_cs2_slot_codes": list(reversed(range(8))),
            },
        }
    elif role in (contract.ROLE_U04_PRIMER, contract.ROLE_U07_PRIMER):
        role_fields = {
            "six_code_map_fidelity_pass": None,
            "all_six_rows_present_and_ordered": None,
            "left_right_corresponding_rows_match": None,
            "row_boundaries_clear": None,
        }
    else:
        role_fields = {
            "blind_visual_equivalence_groups_rows_0_to_5": [],
            "left_right_corresponding_rows_match": None,
            "old_state_outline_or_residual_present": None,
            "distinct_visual_group_count": None,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": OBSERVATION_TEMPLATE_KIND,
        "action": _action_reference(context, ordinal),
        "preview": {
            "file": str(preview_file.resolve()),
            "bytes": len(preview_payload),
            "sha256": campaign.sha256(preview_payload),
            "notice": (
                "monitor preview checks layout/code placement only; reflective colour, "
                "waveform history, ghosting, illumination, and panel variation require "
                "the supervised physical observation"
            ),
        },
        "common_checks": common,
        "role_observation_fields": role_fields,
        "one_operator_reply_may_cover_all_fields": True,
        "thirty_minute_hold_required": False,
        "skipped_hold_is_not_formal_qualification": True,
        "visible_refresh_authorized": False,
        "automatic_next_action_authorized": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--release", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    describe_parser = commands.add_parser("describe", allow_abbrev=False)
    describe_parser.add_argument("--ordinal", type=int, required=True)
    template_parser = commands.add_parser("observation-template", allow_abbrev=False)
    template_parser.add_argument("--ordinal", type=int, required=True)
    preflight_parser = commands.add_parser("preflight", allow_abbrev=False)
    preflight_parser.add_argument("--base-url", required=True)
    preflight_parser.add_argument("--ordinal", type=int, required=True)
    diagnose = commands.add_parser("diagnose-j2-off", allow_abbrev=False)
    diagnose.add_argument("--base-url", required=True)
    diagnose.add_argument("--evidence", type=Path, required=True)
    diagnose.add_argument("--claim-registry", type=Path, default=DEFAULT_CLAIM_REGISTRY)
    diagnose.add_argument("--confirm-j2-off", action="store_true")
    validate_diagnostic = commands.add_parser("validate-j2-off", allow_abbrev=False)
    validate_diagnostic.add_argument("--evidence", type=Path, required=True)
    validate_diagnostic.add_argument(
        "--claim-registry", type=Path, default=DEFAULT_CLAIM_REGISTRY
    )
    run_parser = commands.add_parser("run", allow_abbrev=False)
    run_parser.add_argument("--base-url", required=True)
    run_parser.add_argument("--ordinal", type=int, required=True)
    run_parser.add_argument("--authorize", required=True)
    run_parser.add_argument("--result", type=Path, required=True)
    run_parser.add_argument(
        "--claim-registry", type=Path, default=DEFAULT_CLAIM_REGISTRY
    )
    run_parser.add_argument("--prior-result", type=Path)
    run_parser.add_argument("--prior-observation", type=Path)
    run_parser.add_argument("--j2-off-diagnostic", type=Path)
    run_parser.add_argument(
        "--confirm-no-intervening-visible-refresh", action="store_true"
    )
    run_parser.add_argument("--confirm-j2-on", action="store_true")
    run_parser.add_argument("--confirm-electrical-normal", action="store_true")
    run_parser.add_argument("--temperature-c", type=float, required=True)
    run_parser.add_argument("--poll-count", type=int, default=DEFAULT_POLL_COUNT)
    run_parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
    )
    validate_parser = commands.add_parser("validate-result", allow_abbrev=False)
    validate_parser.add_argument("--result", type=Path, required=True)
    validate_parser.add_argument(
        "--claim-registry", type=Path, default=DEFAULT_CLAIM_REGISTRY
    )
    reconcile = commands.add_parser("reconcile-result", allow_abbrev=False)
    reconcile.add_argument("--base-url", required=True)
    reconcile.add_argument("--source-result", type=Path, required=True)
    reconcile.add_argument("--result", type=Path, required=True)
    reconcile.add_argument("--reconciliation", type=Path, required=True)
    reconcile.add_argument(
        "--claim-registry", type=Path, default=DEFAULT_CLAIM_REGISTRY
    )
    reconcile.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    validate_reconciliation_parser = commands.add_parser(
        "validate-reconciliation", allow_abbrev=False
    )
    validate_reconciliation_parser.add_argument(
        "--reconciliation", type=Path, required=True
    )
    validate_reconciliation_parser.add_argument(
        "--claim-registry", type=Path, default=DEFAULT_CLAIM_REGISTRY
    )
    observation = commands.add_parser("validate-observation", allow_abbrev=False)
    observation.add_argument("--result", type=Path, required=True)
    observation.add_argument("--observation", type=Path, required=True)
    observation.add_argument(
        "--claim-registry", type=Path, default=DEFAULT_CLAIM_REGISTRY
    )
    finalize = commands.add_parser("finalize-observation", allow_abbrev=False)
    finalize.add_argument("--result", type=Path, required=True)
    finalize.add_argument("--observation", type=Path, required=True)
    finalize.add_argument("--claim-registry", type=Path, default=DEFAULT_CLAIM_REGISTRY)
    finalize.add_argument("--operator-report", required=True)
    finalize.add_argument("--temperature-c", type=float, required=True)
    finalize.add_argument("--confirm-reference-preview-checked", action="store_true")
    finalize.add_argument("--confirm-display-matches-reference", action="store_true")
    finalize.add_argument("--confirm-no-unexpected-residual", action="store_true")
    finalize.add_argument("--confirm-electrical-normal", action="store_true")
    finalize.add_argument("--confirm-esp32-no-restart", action="store_true")
    finalize.add_argument("--confirm-clean-white", action="store_true")
    finalize.add_argument("--confirm-map-fidelity", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        context = load_release(args.release)
        if args.command == "describe":
            output = describe(context, args.ordinal)
        elif args.command == "observation-template":
            output = observation_template(context, args.ordinal)
        elif args.command == "preflight":
            output = preflight(context, args.base_url, args.ordinal).as_dict()
        elif args.command == "diagnose-j2-off":
            output = diagnose_j2_off(
                context,
                args.base_url,
                evidence_file=args.evidence,
                claim_registry=args.claim_registry,
                confirm_j2_off=args.confirm_j2_off,
            )
        elif args.command == "validate-j2-off":
            output = validate_j2_off_diagnostic(
                context,
                args.evidence,
                claim_registry=args.claim_registry,
            )
        elif args.command == "run":
            output = run_once(
                context,
                args.base_url,
                args.ordinal,
                authorization=args.authorize,
                result_file=args.result,
                claim_registry=args.claim_registry,
                prior_result_file=args.prior_result,
                prior_observation_file=args.prior_observation,
                j2_off_diagnostic_file=args.j2_off_diagnostic,
                confirm_no_intervening_visible_refresh=(
                    args.confirm_no_intervening_visible_refresh
                ),
                confirm_j2_on=args.confirm_j2_on,
                confirm_electrical_normal=args.confirm_electrical_normal,
                temperature_c=args.temperature_c,
                poll_count=args.poll_count,
                poll_interval_seconds=args.poll_interval_seconds,
            )
        elif args.command == "validate-result":
            output = validate_result(
                context, args.result, claim_registry=args.claim_registry
            )
        elif args.command == "reconcile-result":
            output = reconcile_result(
                context,
                args.base_url,
                source_result_file=args.source_result,
                result_file=args.result,
                reconciliation_file=args.reconciliation,
                claim_registry=args.claim_registry,
                timeout=args.timeout,
            )
        elif args.command == "validate-reconciliation":
            output = validate_reconciliation(
                context,
                args.reconciliation,
                claim_registry=args.claim_registry,
            )
        elif args.command == "validate-observation":
            output = validate_observation(
                context,
                args.observation,
                result_file=args.result,
                claim_registry=args.claim_registry,
            )
        else:
            output = seal_observation(
                context,
                result_file=args.result,
                observation_file=args.observation,
                claim_registry=args.claim_registry,
                operator_report=args.operator_report,
                temperature_c=args.temperature_c,
                confirm_reference_preview_checked=(
                    args.confirm_reference_preview_checked
                ),
                confirm_display_matches_reference=args.confirm_display_matches_reference,
                confirm_no_unexpected_residual=args.confirm_no_unexpected_residual,
                confirm_electrical_normal=args.confirm_electrical_normal,
                confirm_esp32_no_restart=args.confirm_esp32_no_restart,
                confirm_clean_white=args.confirm_clean_white,
                confirm_map_fidelity=args.confirm_map_fidelity,
            )
    except ColorLabPhysicalError as error:
        print(f"EC5 COLOR_LAB error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
