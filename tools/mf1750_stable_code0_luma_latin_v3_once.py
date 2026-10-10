#!/usr/bin/env python3
"""Fail-closed one-action host for stable-code0 luma Latin V3.

The host never flashes, resets, controls power, retries, recovers, or chains
actions.  It consumes one explicitly selected ordinal only, requires a sealed
same-boot J2-OFF diagnostic plus fresh human J2/GND assertions, and accepts one
strict COMPLETE result.  L4 is never selected automatically.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import ipaddress
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_stable_code0_luma_latin_v3_pack as pack  # noqa: E402

_BASE_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_once.py"
)
_SPEC = importlib.util.spec_from_file_location("_mf1750_stable_code0_luma_latin_v3_host", _BASE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load reviewed one-action mechanics: {_BASE_PATH}")
v3 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v3)
v1 = v3.v1
base = v3.base

REPORT = pack.build_report()
v3.pack = pack
v3.REPORT = REPORT
base.pack = pack
base._REPORT = REPORT
base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 65.0

base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = pack.DEVICE_API_VERSION
base.runner.IDENTITY_REVISION = pack.IDENTITY_REVISION
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = pack.CLASSIFICATION
base.runner.DEVICE_KIND_PREFIX = "mf1750-ec5-stable-code0-luma-latin-v3"
base.runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-stable-code0-luma-latin-v3"
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY
base.runner.FIRMWARE_SHA256 = str(pack.ARTIFACTS[pack.VARIANT_KEY]["bin_sha256"])
base.runner.FIRMWARE_BYTES = int(pack.ARTIFACTS[pack.VARIANT_KEY]["bin_bytes"])
ELF_SHA256 = str(pack.ARTIFACTS[pack.VARIANT_KEY]["elf_sha256"])
ELF_BYTES = int(pack.ARTIFACTS[pack.VARIANT_KEY]["elf_bytes"])
BUILD_DIR = REPO_ROOT / ".pio" / pack.BUILD_ROOT / pack.ENVIRONMENT
base.runner.ENDPOINTS = {
    name: f"{pack.BASE_ROUTE}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = pack.ARM_INTENT
base.runner.EXECUTE_INTENT = pack.EXECUTE_INTENT


def _runner_actions() -> tuple[dict[str, Any], ...]:
    actions = deepcopy(base._actions())
    for action, source in zip(actions, REPORT["actions"], strict=True):
        ordinal = action["ordinal"]
        action["boot_admission"] = {
            "campaign_boot_binding_key": pack.NVS_BOOT_KEY,
            "admission": "FRESH_CURSOR_AND_BOOT_KEY_ABSENT_ONLY"
            if ordinal == 1
            else "SAME_PERSISTED_CAMPAIGN_BOOT_ONLY",
            "required_prior_terminal_state": None if ordinal == 1 else "COMPLETE",
            "required_prior_ordinal": None if ordinal == 1 else ordinal - 1,
            "firmware_arm_gate": True,
            "firmware_execute_gate": True,
            "firmware_dispatch_gate": True,
            "reboot_resume_allowed": False,
            "post_containment_resume_allowed": False,
        }
        action["palette_source"] = source["palette_source"]
        action["global_header"] = source["global_header"]
        action["driver_entry"] = "epdDisplayCompiledChromaGrid"
    return tuple(actions)


base.runner.ACTIONS = _runner_actions()
base.runner.DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in base.runner.ACTIONS
)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output/hardware/.mf1750_stable_code0_luma_latin_v3_claims"
)
base.runner.DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output/hardware/MF1750_STABLE_CODE0_LUMA_LATIN_20260901_V3"
)
DIAGNOSTIC_OUTPUT = base.runner.DEFAULT_OUTPUT / "j2-off-diagnostic.json"
ACTION_OUTPUTS = {
    1: base.runner.DEFAULT_OUTPUT / "action-01-l1-active-source-code7.json",
    2: base.runner.DEFAULT_OUTPUT
    / "action-02-l2-commented-middle-latin-c0-c7.json",
    3: base.runner.DEFAULT_OUTPUT / "action-03-l3-active-target-code0.json",
    4: base.runner.DEFAULT_OUTPUT
    / "action-04-l4-identical-active-target-code0-repeat.json",
}
ALTERNATIVE_V2_OUTPUT_ROOT = (
    REPO_ROOT
    / ".test-output/hardware/MF1750_LUMA_GRAY_MECHANISM_POSITION_BALANCED_20260901_V2"
)
ALTERNATIVE_V2_CLAIMS_ROOT = (
    REPO_ROOT
    / ".test-output/hardware/.mf1750_luma_gray_mechanism_position_balanced_v2_claims"
)

_SHA = re.compile(r"^[0-9a-f]{64}$")
_MAX_JSON_BYTES = 16 * 1024 * 1024


def _private_origin(value: str) -> str:
    """Return only an exact private/local literal-IPv4 HTTP origin."""

    if not isinstance(value, str):
        raise base.runner.RecheckError(
            "base URL must be a private/local literal IPv4 HTTP origin"
        )
    parsed = urllib_parse.urlsplit(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise base.runner.RecheckError("base URL port is invalid") from error
    if (
        parsed.scheme != "http"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != ""
        or parsed.query
        or parsed.fragment
        or parsed.netloc.endswith(":")
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise base.runner.RecheckError("base URL must be an exact plain HTTP origin")
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError as error:
        raise base.runner.RecheckError(
            "base URL must use a literal IPv4 address"
        ) from error
    allowed = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
    )
    if not isinstance(address, ipaddress.IPv4Address) or not any(
        address in network for network in allowed
    ):
        raise base.runner.RecheckError(
            "base URL must use a private/local literal IPv4 address"
        )
    authority = str(address) if port is None else f"{address}:{port}"
    return f"http://{authority}"


def _request_timeout(value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0 < float(value) <= 30
    ):
        raise base.runner.RecheckError("HTTP timeout must be in (0,30]")
    return float(value)


class _NoRedirect(urllib_request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def _direct_http_request(
    base_url: str,
    path: str,
    *,
    method: str,
    headers: Mapping[str, str] | None,
    timeout: float,
) -> tuple[int, Mapping[str, Any]]:
    """Perform one direct request; never consult proxies or follow redirects."""

    request = urllib_request.Request(
        base_url + path,
        method=method,
        headers={"Accept": "application/json", **dict(headers or {})},
    )
    opener = urllib_request.build_opener(urllib_request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=_request_timeout(timeout)) as response:  # noqa: S310
            status = response.status
            payload = response.read(_MAX_JSON_BYTES + 1)
    except urllib_error.HTTPError as error:
        status = error.code
        payload = error.read(_MAX_JSON_BYTES + 1)
    except (OSError, urllib_error.URLError) as error:
        raise base.runner.RecheckError(
            f"direct {method} {path} failed: {error}"
        ) from error
    if len(payload) > _MAX_JSON_BYTES:
        raise base.runner.RecheckError(f"direct {method} {path} response is too large")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise base.runner.RecheckError(
            f"direct {method} {path} response is not UTF-8 JSON"
        ) from error
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError(
            f"direct {method} {path} response root is not an object"
        )
    return status, value


def _verify_local_artifacts() -> None:
    if not pack.artifacts_are_sealed():
        raise base.runner.RecheckError("V3 artifacts are not sealed")
    for name, size, digest in (
        ("firmware.bin", base.runner.FIRMWARE_BYTES, base.runner.FIRMWARE_SHA256),
        ("firmware.elf", ELF_BYTES, ELF_SHA256),
    ):
        path = BUILD_DIR / name
        if not path.is_file():
            raise base.runner.RecheckError(
                f"reviewed stable-code0 luma Latin V3 artifact missing: {path}"
            )
        data = path.read_bytes()
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise base.runner.RecheckError(
                f"reviewed stable-code0 luma Latin V3 artifact differs: {path}"
            )


def _validate_alternative_v2_branch_unused() -> None:
    """A single W11 white anchor cannot authorize both alternative branches."""

    conflicting = []
    for root in (ALTERNATIVE_V2_OUTPUT_ROOT, ALTERNATIVE_V2_CLAIMS_ROOT):
        if root.is_dir() and any(path.is_file() for path in root.iterdir()):
            try:
                label = root.relative_to(REPO_ROOT).as_posix()
            except ValueError:
                label = str(root.resolve())
            conflicting.append(label)
    if conflicting:
        raise base.runner.RecheckError(
            "stable-code0 V3 and luma/gray V2 are alternative W11 successors; "
            "a fresh post-containment white anchor and new binding are required: "
            + ", ".join(conflicting)
        )


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    for key in (
        "full_screen_global_refresh",
        "history_brightness_screening",
        "target_repeat_stability_probe",
        "busy_qualified_arm_execute_dispatch",
        "device_enforced_same_boot",
        "brightness_candidates_only",
        "l4_identical_target_repeat",
        "l4_separate_manual_action",
        "independent_factory_otp_white_containment_required",
    ):
        if value.get(key) is not True:
            raise base.runner.RecheckError(f"stable-code0 luma Latin V3 capability {key} differs")
    for key in (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "command_0x86",
        "unknown_commands",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "same_palette_hold_probe",
        "cross_palette_hold_probe",
        "local_hold_claimed",
        "l4_automatic_dispatch",
    ):
        if value.get(key) is not False:
            raise base.runner.RecheckError(
                f"stable-code0 luma Latin V3 forbidden capability {key} differs"
            )
    if value.get("qualified_brightness_levels") != 0:
        raise base.runner.RecheckError("stable-code0 luma Latin V3 qualified-level count differs")
    if (
        value.get("l4_separate_manual_action") is not True
        or value.get("l4_automatic_dispatch") is not False
    ):
        raise base.runner.RecheckError("stable-code0 luma Latin V3 L4 selection policy differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="version")  # noqa: SLF001
    if (
        value.get("layout_id") != pack.VARIANT_KEY
        or value.get("action_count") != 4
        or value.get("runtime_lut_write") is not True
    ):
        raise base.runner.RecheckError("stable-code0 luma Latin V3 version contract differs")
    _validate_capabilities(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    if (
        value.get("layout_id") != pack.VARIANT_KEY
        or value.get("actions") != list(base.runner.ACTIONS)
        or value.get("action_count") != 4
    ):
        raise base.runner.RecheckError("stable-code0 luma Latin V3 manifest/action table differs")
    layout = value.get("history_layout", {})
    expected = {
        "candidate_cells_per_controller": 64,
        "candidate_cells_total_observations": 128,
        "middle_repeat_count_per_controller": 8,
        "controller_color_equivalence_claimed": False,
        "grid_rows": 8,
        "grid_columns_per_controller": 8,
        "grid_x0_local": 20,
        "grid_y0": 40,
        "grid_x1_local_exclusive": 492,
        "grid_y1_exclusive": 560,
        "cell_width": 52,
        "cell_height": 58,
        "gap_x": 8,
        "gap_y": 8,
        "source_global_header": "active",
        "source_code": 7,
        "middle_global_header": "commented",
        "middle_codes": list(range(8)),
        "target_global_header": "active",
        "target_code": 0,
        "profile_sequence": list(pack.GLOBAL_HEADERS),
        "cs1_layout": "latin_code=(row+column)%8",
        "cs2_layout": "rotate_180_of_cs1",
        "cs2_decoder": (
            "logical=(7-row,7-column);code=(logical_row+logical_column)%8"
        ),
        "cs2_role": "RED_FAMILY_PRIMARY_OBSERVATION",
        "cs1_role": "CONTROLLER_SPECIFIC_INTERNAL_CONTROL",
        "target_hue_id": pack.TARGET_HUE_ID,
        "qualified_brightness_levels": 0,
        "spatial_dither": False,
        "ptlw_command_issued": False,
        "cropped_dtm": False,
        "all_action_dtm_transport": "packed_frame_per_controller",
        "l4_identical_target_repeat": True,
        "l4_automatic_dispatch": False,
        "l4_autochain": False,
    }
    if any(layout.get(key) != wanted for key, wanted in expected.items()):
        raise base.runner.RecheckError("stable-code0 luma Latin V3 manifest layout differs")
    authority = layout.get("source_authority")
    source = REPORT["contract"]["source_authority"]
    if (
        not isinstance(authority, Mapping)
        or authority.get("authority_kind") != source["authority_kind"]
        or authority.get("required_before_any_device_request") is not True
        or authority.get("w11_action_id") != source["w11"]["action_id"]
        or authority.get("w11_action_file_sha256")
        != source["files"]["w11_complete"]["file_sha256"]
        or authority.get("camera_review_file_sha256")
        != source["files"]["camera_visible_clean_white_review"]["file_sha256"]
        or authority.get("camera_review_state")
        != "CAMERA_VISIBLE_CLEAN_WHITE_CONTAINMENT_REVIEW"
        or authority.get("camera_relative_only") is not True
        or authority.get("absolute_white_point_proven") is not False
        or authority.get("spatial_uniformity_proven") is not False
        or authority.get("schedule_policy") != source["schedule_policy"]
    ):
        raise base.runner.RecheckError("stable-code0 source authority surface differs")
    _validate_capabilities(value)


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_busy: int
) -> str:
    if not 1 <= ordinal <= 4:
        raise base.runner.RecheckError("stable-code0 runnable ordinal differs")
    if expected_busy not in (0, 1) or (expected_busy == 0 and ordinal != 1):
        raise base.runner.RecheckError("stable-code0 BUSY admission differs")
    if value.get("busy") != expected_busy:
        raise base.runner.RecheckError("stable-code0 raw ready BUSY differs")
    nonce = v1._BASE_VALIDATE_READY_STATUS(  # noqa: SLF001
        value, ordinal, expected_busy=expected_busy
    )
    expected_count = ordinal - 1
    for key in ("arm_request_count", "execute_request_count", "total_driver_call_count"):
        if value.get(key) != expected_count:
            raise base.runner.RecheckError(f"stable-code0 ready status {key} differs")
    if (
        value.get("campaign_boot_key_present") is not True
        or value.get("persisted_campaign_boot_nonce") != nonce
        or value.get("campaign_boot_matches_current") is not True
        or value.get("device_enforced_same_boot") is not True
        or value.get("reboot_resume_allowed") is not False
        or value.get("post_containment_resume_allowed") is not False
    ):
        raise base.runner.RecheckError("stable-code0 persisted boot binding differs")
    return nonce


def _validate_prior_terminal_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    if ordinal <= 1:
        raise base.runner.RecheckError("stable-code0 prior ordinal differs")
    v3._validate_complete_report(value, ordinal - 1, boot_nonce)  # noqa: SLF001


def _preflight(
    base_url: str,
    ordinal: int,
    *,
    expected_busy: int,
    requester: Any,
) -> tuple[str, list[dict[str, Any]], Mapping[str, Any]]:
    boot_nonce, transcript, report = v1._BASE_PREFLIGHT(  # noqa: SLF001
        base_url,
        ordinal,
        expected_busy=expected_busy,
        requester=requester,
    )
    if ordinal == 1:
        v1._validate_fresh_no_execute_report(report, boot_nonce)  # noqa: SLF001
    else:
        _validate_prior_terminal_report(report, ordinal, boot_nonce)
    return boot_nonce, transcript, report


# Rebind all dynamic validators inside the private mature runner facade.
v1._validate_version = _validate_version
v1._validate_manifest = _validate_manifest
v1._validate_ready_status = _validate_ready_status
v1._preflight = _preflight
base._validate_version = _validate_version
base._validate_manifest = _validate_manifest
base.runner._validate_version = _validate_version
base.runner._validate_manifest = _validate_manifest
base.runner._validate_ready_status = _validate_ready_status
base.runner._preflight = _preflight
base.runner._origin = _private_origin
base.runner._http_request = _direct_http_request
v3._validate_ready_status = _validate_ready_status
v3._validate_prior_terminal_report = _validate_prior_terminal_report
v3._preflight = _preflight


def _read_integrity_json(path: Path, *, label: str) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise base.runner.RecheckError(f"{label} missing or unsafe: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise base.runner.RecheckError(f"{label} is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise base.runner.RecheckError(f"{label} root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    recorded = integrity.get("sha256") if isinstance(integrity, Mapping) else None
    actual = hashlib.sha256(
        json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    if recorded != actual:
        raise base.runner.RecheckError(f"{label} canonical integrity differs")
    return value


def diagnose_j2_off(
    base_url: str,
    *,
    confirm_j2_off: bool,
    confirm_no_intervening_refresh_since_w11_white: bool,
    output: Path = DIAGNOSTIC_OUTPUT,
    requester: Any = None,
) -> dict[str, Any]:
    """Capture one immutable four-GET, zero-mutation diagnostic."""

    if confirm_j2_off is not True:
        raise base.runner.RecheckError("V3 diagnostic requires explicit J2-OFF confirmation")
    if confirm_no_intervening_refresh_since_w11_white is not True:
        raise base.runner.RecheckError(
            "V3 is an alternative W11 branch and requires confirmation that no "
            "panel refresh intervened since the bound W11 white"
        )
    _validate_alternative_v2_branch_unused()
    pack.validate_source_authority()
    _verify_local_artifacts()
    selected = requester or _direct_http_request
    origin = _private_origin(base_url)
    boot_nonce, transcript, report = v3._preflight(  # noqa: SLF001
        origin, 1, expected_busy=0, requester=selected
    )
    value = base.runner._seal(  # noqa: SLF001
        {
            "schema_version": 2,
            "kind": (
                "mf1750-ec5-stable-code0-luma-latin-v3-"
                "j2-off-diagnostic"
            ),
            "created_at": base.runner._now(),  # noqa: SLF001
            "campaign_id": pack.CAMPAIGN_ID,
            "contract_id": REPORT["contract_id"],
            "firmware": {
                "bytes": base.runner.FIRMWARE_BYTES,
                "sha256": base.runner.FIRMWARE_SHA256,
            },
            "elf": {"bytes": ELF_BYTES, "sha256": ELF_SHA256},
            "source_gate": deepcopy(pack.validate_source_authority()),
            "base_url": origin,
            "boot_nonce": boot_nonce,
            "j2_confirmed_off": True,
            "no_intervening_panel_refresh_since_w11_white_confirmed": True,
            "alternative_branch_from_w11_only": True,
            "next_ordinal": 1,
            "report": deepcopy(dict(report)),
            "transcript": transcript,
            "network": {"get": 4, "post": 0},
            "visible_refreshes": 0,
            "no_retry": True,
            "no_fallback": True,
            "no_recovery": True,
            "no_autochain": True,
        }
    )
    base.runner._write_new(Path(output), value)  # noqa: SLF001
    return value


def _validate_diagnostic(path: Path, base_url: str) -> dict[str, Any]:
    value = _read_integrity_json(path, label="V3 J2-OFF diagnostic")
    transcript = value.get("transcript")
    expected_paths = [
        base.runner.ENDPOINTS[name]
        for name in ("version", "manifest", "status", "report")
    ]
    if (
        value.get("kind")
        != "mf1750-ec5-stable-code0-luma-latin-v3-j2-off-diagnostic"
        or value.get("campaign_id") != pack.CAMPAIGN_ID
        or value.get("contract_id") != REPORT["contract_id"]
        or value.get("firmware")
        != {
            "bytes": base.runner.FIRMWARE_BYTES,
            "sha256": base.runner.FIRMWARE_SHA256,
        }
        or value.get("elf") != {"bytes": ELF_BYTES, "sha256": ELF_SHA256}
        or value.get("source_gate") != pack.validate_source_authority()
        or value.get("base_url") != _private_origin(base_url)
        or value.get("j2_confirmed_off") is not True
        or value.get("no_intervening_panel_refresh_since_w11_white_confirmed")
        is not True
        or value.get("alternative_branch_from_w11_only") is not True
        or value.get("next_ordinal") != 1
        or value.get("network") != {"get": 4, "post": 0}
        or value.get("visible_refreshes") != 0
        or not isinstance(transcript, list)
        or len(transcript) != 4
        or [item.get("path") for item in transcript] != expected_paths
        or any(item.get("method") != "GET" for item in transcript)
        or any(item.get("status") != 200 for item in transcript)
    ):
        raise base.runner.RecheckError("V3 J2-OFF diagnostic semantics differ")
    boot_nonce = value.get("boot_nonce")
    if not isinstance(boot_nonce, str) or re.fullmatch(r"[0-9a-f]{16}", boot_nonce) is None:
        raise base.runner.RecheckError("V3 diagnostic boot nonce differs")
    return value


def _same_boot_requester(expected_boot_nonce: str, requester: Any) -> Any:
    def checked(*args: Any, **kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        status, value = requester(*args, **kwargs)
        observed = value.get("boot_nonce") if isinstance(value, Mapping) else None
        if observed is not None and observed != expected_boot_nonce:
            raise base.runner.RecheckError(
                "V3 live response boot nonce differs from J2-OFF diagnostic"
            )
        return status, value

    return checked


def run_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: Any = None,
    poll_seconds: float = 65.0,
    poll_count: int = 60,
    confirm_j2_on: bool = False,
    confirm_gnd_normal: bool = False,
    confirm_source_w11_camera_white: bool = False,
    confirm_no_intervening_refresh_since_w11_white: bool = False,
    confirm_optional_l4_repeat: bool = False,
) -> dict[str, Any]:
    if confirm_j2_on is not True:
        raise base.runner.RecheckError("V3 run requires explicit J2-ON confirmation")
    if confirm_gnd_normal is not True:
        raise base.runner.RecheckError("V3 run requires explicit GND-normal confirmation")
    if confirm_source_w11_camera_white is not True:
        raise base.runner.RecheckError(
            "V3 run requires explicit W11 camera-visible clean-white source authority confirmation"
        )
    if ordinal == 1 and confirm_no_intervening_refresh_since_w11_white is not True:
        raise base.runner.RecheckError(
            "V3 L1 requires confirmation that no panel refresh intervened since "
            "the bound W11 white; otherwise a fresh white successor and binding "
            "are required"
        )
    if ordinal > 1 and confirm_no_intervening_refresh_since_w11_white is True:
        raise base.runner.RecheckError(
            "V3 L2-L4 follow prior same-boot COMPLETE actions and must not reassert "
            "the now-false W11 no-intervening-refresh statement"
        )
    if ordinal == 4 and confirm_optional_l4_repeat is not True:
        raise base.runner.RecheckError(
            "L4 is optional and requires its own explicit repeat confirmation"
        )
    if ordinal != 4 and confirm_optional_l4_repeat is True:
        raise base.runner.RecheckError("L4 repeat confirmation is forbidden for L1-L3")
    if ordinal == 1:
        _validate_alternative_v2_branch_unused()
    pack.validate_source_authority()
    _verify_local_artifacts()
    diagnostic = _validate_diagnostic(DIAGNOSTIC_OUTPUT, base_url)
    selected = requester or _direct_http_request
    selected = _same_boot_requester(str(diagnostic["boot_nonce"]), selected)
    return v3.run_once(
        base_url,
        ordinal,
        claims=claims,
        output=output,
        requester=selected,
        poll_seconds=poll_seconds,
        poll_count=poll_count,
    )


def dry_validate(*, verify_artifacts: bool = True) -> dict[str, Any]:
    pack_result = pack.dry_validate(verify_artifacts=verify_artifacts)
    if verify_artifacts:
        _verify_local_artifacts()
    contract = REPORT["contract"]
    if (
        REPORT["contract_id"] != base.runner.CONTRACT_ID
        or len(REPORT["actions"]) != 4
        or len(contract["recipes"]) != 128
        or contract["factory_otp_in_main_campaign"] is not False
        or contract["independent_factory_otp_white_containment_required"] is not True
        or contract["autochain"] is not False
    ):
        raise base.runner.RecheckError("stable-code0 luma Latin V3 offline identity differs")
    counts = {
        controller: {
            middle: sum(
                pack.middle_code(controller, row, column) == middle
                for row in range(8)
                for column in range(8)
            )
            for middle in range(8)
        }
        for controller in (0, 1)
    }
    if counts != {0: {code: 8 for code in range(8)}, 1: {code: 8 for code in range(8)}}:
        raise base.runner.RecheckError("stable-code0 luma Latin V3 repeat placement differs")
    return {
        "kind": "mf1750-stable-code0-luma-latin-v3-runner-validation",
        "result": "PASS",
        "offline_only": True,
        "network_requests": 0,
        "hardware_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract_id": REPORT["contract_id"],
        "actions": 4,
        "physical_cell_recipes": 128,
        "middle_codes": 8,
        "repeats_per_middle_per_controller": 8,
        "source_gate": deepcopy(pack.validate_source_authority()),
        "l4_explicit_optional_no_autochain": True,
        "controller_colour_equivalence_claimed": False,
        "qualified_brightness_levels": 0,
        "qualified_colours": 0,
        "pack_validation": pack_result,
        "artifacts_verified": verify_artifacts,
        "firmware": {
            "bytes": base.runner.FIRMWARE_BYTES,
            "sha256": base.runner.FIRMWARE_SHA256,
        },
        "elf": {"bytes": ELF_BYTES, "sha256": ELF_SHA256},
    }


def describe() -> dict[str, Any]:
    return {
        **dry_validate(verify_artifacts=pack.artifacts_are_sealed()),
        "contract": deepcopy(REPORT["contract"]),
        "actions_table": deepcopy(base.runner.ACTIONS),
        "endpoints": deepcopy(base.runner.ENDPOINTS),
        "claims_root": str(base.runner.DEFAULT_CLAIMS),
        "output_root": str(base.runner.DEFAULT_OUTPUT),
    }


def validate_terminal_evidence(path: Path) -> dict[str, Any]:
    """Deep-validate an exact L3 or L4 COMPLETE result without device I/O."""

    pack.validate_source_authority()
    _verify_local_artifacts()
    resolved = Path(path).resolve()
    accepted = {ACTION_OUTPUTS[3].resolve(): 3, ACTION_OUTPUTS[4].resolve(): 4}
    if resolved not in accepted:
        raise base.runner.RecheckError(
            "white containment accepts only the fixed L3 or L4 COMPLETE file"
        )
    value = _read_integrity_json(resolved, label="V3 terminal evidence")
    action = value.get("action")
    terminal = value.get("terminal_report")
    transcript = value.get("transcript")
    if not isinstance(action, Mapping) or not isinstance(terminal, Mapping):
        raise base.runner.RecheckError("V3 terminal action/report missing")
    ordinal = accepted[resolved]
    if action.get("ordinal") != ordinal:
        raise base.runner.RecheckError("V3 terminal ordinal differs")
    expected = base.runner.ACTIONS[ordinal - 1]
    if dict(action) != expected:
        raise base.runner.RecheckError("V3 terminal action identity differs")
    boot_nonce = value.get("boot_nonce")
    if not isinstance(boot_nonce, str) or re.fullmatch(r"[0-9a-f]{16}", boot_nonce) is None:
        raise base.runner.RecheckError("V3 terminal boot nonce differs")
    v3._validate_complete_report(terminal, ordinal, boot_nonce)  # noqa: SLF001
    if (
        value.get("kind") != "mf1750-ec5-stable-code0-luma-latin-v3-result"
        or value.get("firmware_sha256") != base.runner.FIRMWARE_SHA256
        or value.get("outcome") != "complete_pass"
        or value.get("visible_refreshes") != 1
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
        or value.get("network")
        != {"get": 5, "arm_post": 1, "execute_post": 1}
    ):
        raise base.runner.RecheckError("V3 terminal COMPLETE/driver semantics differ")
    expected_methods = ["GET", "GET", "GET", "GET", "POST", "POST", "GET"]
    expected_paths = [
        base.runner.ENDPOINTS[name]
        for name in ("version", "manifest", "status", "report", "arm", "execute", "report")
    ]
    if (
        not isinstance(transcript, list)
        or len(transcript) != 7
        or [item.get("method") for item in transcript] != expected_methods
        or [item.get("path") for item in transcript] != expected_paths
        or [item.get("status") for item in transcript] != [200, 200, 200, 200, 201, 202, 200]
    ):
        raise base.runner.RecheckError("V3 terminal transcript missing")
    status = transcript[2].get("response")
    prior = transcript[3].get("response")
    arm = transcript[4].get("response")
    execute = transcript[5].get("response")
    final = transcript[6].get("response")
    version = transcript[0].get("response")
    manifest = transcript[1].get("response")
    if (
        not isinstance(version, Mapping)
        or not isinstance(manifest, Mapping)
        or not isinstance(status, Mapping)
        or not isinstance(prior, Mapping)
        or not isinstance(arm, Mapping)
        or not isinstance(execute, Mapping)
        or final != terminal
    ):
        raise base.runner.RecheckError("V3 terminal transcript response binding differs")
    _validate_version(version)
    _validate_manifest(manifest)
    observed_boot = _validate_ready_status(status, ordinal, expected_busy=1)
    if observed_boot != boot_nonce:
        raise base.runner.RecheckError("V3 terminal status boot differs")
    _validate_prior_terminal_report(prior, ordinal, boot_nonce)
    expected_arm_headers = base.runner._headers(  # noqa: SLF001
        expected, boot_nonce, base.runner.ARM_INTENT
    )
    if transcript[4].get("headers") != expected_arm_headers:
        raise base.runner.RecheckError("V3 terminal ARM wire headers differ")
    arm_nonce = arm.get("arm_nonce")
    arm_exact = {
        "accepted": True,
        "armed": True,
        "not_hardware_authorization": True,
        "boot_nonce": boot_nonce,
        "ordinal": ordinal,
        "descriptor_id": expected["descriptor_id"],
        "action_id": expected["action_id"],
        "role": expected["role"],
        "branch": expected["branch"],
        "driver_entry": expected["driver_entry"],
        "palette_source": expected["palette_source"],
        "global_header": expected["global_header"],
        "phase": 1,
        "phase_name": "ARMED",
    }
    if (
        any(arm.get(key) != wanted for key, wanted in arm_exact.items())
        or not isinstance(arm_nonce, str)
        or re.fullmatch(r"[0-9a-f]{16}", arm_nonce) is None
    ):
        raise base.runner.RecheckError("V3 terminal ARM response differs")
    expected_execute_headers = base.runner._headers(  # noqa: SLF001
        expected, boot_nonce, base.runner.EXECUTE_INTENT
    )
    expected_execute_headers["X-EC5-Arm-Nonce"] = arm_nonce
    if transcript[5].get("headers") != expected_execute_headers:
        raise base.runner.RecheckError("V3 terminal EXECUTE wire headers differ")
    execute_exact = {
        "accepted": True,
        "execute_consumed": True,
        "boot_nonce": boot_nonce,
        "ordinal": ordinal,
        "descriptor_id": expected["descriptor_id"],
        "action_id": expected["action_id"],
        "role": expected["role"],
        "branch": expected["branch"],
        "driver_entry": expected["driver_entry"],
        "palette_source": expected["palette_source"],
        "global_header": expected["global_header"],
        "phase": 2,
        "phase_name": "CONSUMED",
        "no_retry": True,
        "no_recovery": True,
    }
    if any(execute.get(key) != wanted for key, wanted in execute_exact.items()):
        raise base.runner.RecheckError("V3 terminal EXECUTE response differs")
    claim_path = value.get("claim_file")
    expected_claim_path = (base.runner.DEFAULT_CLAIMS / f"{expected['action_id']}.json").resolve()
    if not isinstance(claim_path, str) or Path(claim_path).resolve() != expected_claim_path:
        raise base.runner.RecheckError("V3 terminal claim path missing")
    claim = _read_integrity_json(expected_claim_path, label="V3 permanent claim")
    if (
        claim.get("action") != expected
        or claim.get("boot_nonce") != boot_nonce
        or claim.get("firmware_sha256") != base.runner.FIRMWARE_SHA256
        or claim.get("state") != "claimed_before_first_mutation"
        or claim.get("no_retry") is not True
        or claim.get("no_recovery") is not True
        or claim.get("no_autochain") is not True
    ):
        raise base.runner.RecheckError("V3 permanent claim semantics differ")
    claim_payload = expected_claim_path.read_bytes()
    return {
        "terminal_state": "COMPLETE",
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": REPORT["contract_id"],
        "ordinal": ordinal,
        "descriptor_id": expected["descriptor_id"],
        "action_id": expected["action_id"],
        "driver_call_count_for_action": 1,
        "total_driver_call_count": ordinal,
        "visible_refreshes": 1,
        "source_success_claimed": True,
        "boot_nonce": boot_nonce,
        "claim_path": expected_claim_path.relative_to(REPO_ROOT).as_posix(),
        "claim_bytes": len(claim_payload),
        "claim_file_sha256": hashlib.sha256(claim_payload).hexdigest(),
        "claim_canonical_integrity_sha256": claim["integrity"]["sha256"],
        "file_sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        "canonical_integrity_sha256": value["integrity"]["sha256"],
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("dry-validate")
    sub.add_parser("prebuild-validate")
    sub.add_parser("describe")
    diag = sub.add_parser("diagnose-j2-off", allow_abbrev=False)
    diag.add_argument("--base-url", required=True)
    diag.add_argument("--confirm-j2-off", action="store_true", required=True)
    diag.add_argument(
        "--confirm-no-intervening-refresh-since-w11-white",
        action="store_true",
        required=True,
    )
    run = sub.add_parser("run", allow_abbrev=False)
    run.add_argument("--base-url", required=True)
    run.add_argument("--ordinal", type=int, choices=range(1, 5), required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--confirm-gnd-normal", action="store_true", required=True)
    run.add_argument(
        "--confirm-source-w11-camera-white", action="store_true", required=True
    )
    run.add_argument(
        "--confirm-no-intervening-refresh-since-w11-white",
        action="store_true",
    )
    run.add_argument("--confirm-optional-l4-repeat", action="store_true")
    run.add_argument("--poll-seconds", type=float, default=65.0)
    run.add_argument("--poll-count", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "dry-validate":
            value = dry_validate(verify_artifacts=True)
        elif args.command == "prebuild-validate":
            value = dry_validate(verify_artifacts=False)
        elif args.command == "describe":
            value = describe()
        elif args.command == "diagnose-j2-off":
            value = diagnose_j2_off(
                args.base_url,
                confirm_j2_off=args.confirm_j2_off,
                confirm_no_intervening_refresh_since_w11_white=(
                    args.confirm_no_intervening_refresh_since_w11_white
                ),
                output=DIAGNOSTIC_OUTPUT,
            )
        else:
            value = run_once(
                args.base_url,
                args.ordinal,
                claims=base.runner.DEFAULT_CLAIMS,
                output=ACTION_OUTPUTS[args.ordinal],
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
                confirm_j2_on=args.confirm_j2_on,
                confirm_gnd_normal=args.confirm_gnd_normal,
                confirm_source_w11_camera_white=args.confirm_source_w11_camera_white,
                confirm_no_intervening_refresh_since_w11_white=(
                    args.confirm_no_intervening_refresh_since_w11_white
                ),
                confirm_optional_l4_repeat=args.confirm_optional_l4_repeat,
            )
    except base.runner.RecheckError as error:
        print(f"stable-code0 luma Latin V3 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
