#!/usr/bin/env python3
"""Fail-closed one-action runner for red/pink history candidates.

This runner never flashes, resets, controls J2/power, retries, recovers, or
autochains.  It verifies the reviewed local BIN/ELF before any device request,
requires raw BUSY=1 for every ordinal, and accepts only strict terminal BUSY
evidence.  A visual failure before ordinal 6 must use the independent fresh-
identity factory-OTP white containment firmware; this campaign's ordinals
cannot be skipped. Ordinal 5 is never automatic and requires a fresh operator
decision after ordinal 4 observation.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import ipaddress
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Callable, Mapping, Sequence
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_hue_brightness_redpink_v2_pack as pack  # noqa: E402


_V3_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_hue_brightness_redpink_v2_private_v3_host", _V3_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load BUSY-qualified host mechanics: {_V3_PATH}")
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
base.runner.DEVICE_API_VERSION = "MF1750_EC5_TARGET_HUE_REDPINK_BRIGHTNESS_DEVICE_V2"
base.runner.IDENTITY_REVISION = (
    "runtime-lut-target-hue-redpink-brightness-factory-white-"
    "single-app-boot-flash-verify-v3"
)
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = (
    "EXPERIMENTAL_L535_REDPINK_HISTORY_BRIGHTNESS_CANDIDATES_NOT_QUALIFIED_LEVELS"
)
base.runner.DEVICE_KIND_PREFIX = "mf1750-ec5-target-hue-redpink-brightness-v2"
base.runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-target-hue-redpink-brightness-v2"
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY

FIRMWARE_SHA256 = "e50acc57e0ef98953f1e40695eba17ae03a3df85b25941eacf332bad78c084fe"
FIRMWARE_BYTES = 801_936
ELF_SHA256 = "925bbcab8b730d245ca569abd46fa3daa25ba16b4befab2788f35989db5fe8fb"
ELF_BYTES = 13_297_040
BUILD_DIR = (
    REPO_ROOT
    / ".pio"
    / "build-runtime-lut-hue-brightness-redpink-v2"
    / "ec5_runtime_lut_hue_brightness_redpink_v2"
)
base.runner.FIRMWARE_SHA256 = FIRMWARE_SHA256
base.runner.FIRMWARE_BYTES = FIRMWARE_BYTES
base.runner.ENDPOINTS = {
    name: f"/api/ec5/target-hue-redpink-brightness-v2/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = "ARM_ONE_FIXED_REDPINK_V2_HUE_BRIGHTNESS_CANDIDATE_ACTION"
base.runner.EXECUTE_INTENT = (
    "EXECUTE_ARMED_REDPINK_V2_HUE_BRIGHTNESS_CANDIDATE_ACTION_ONCE"
)


def _actions() -> tuple[dict[str, Any], ...]:
    """Match the exact action-object shape emitted by this firmware."""

    actions = deepcopy(base._actions())
    contract_actions = REPORT["contract"]["actions"]
    if len(actions) != len(contract_actions):
        raise base.runner.RecheckError("red/pink action table length differs")
    for action, contract_action in zip(actions, contract_actions, strict=True):
        factory_otp = contract_action["palette_source"] == "FACTORY_OTP"
        action["palette_source"] = contract_action["palette_source"]
        action["global_header"] = contract_action["global_header"]
        action["boot_admission"] = deepcopy(contract_action["boot_admission"])
        action["driver_entry"] = (
            "epdDisplayCompiledFactoryOtpWhiteRecovery"
            if factory_otp
            else "epdDisplayCompiledChromaGrid"
        )
    return tuple(actions)


base.runner.ACTIONS = _actions()
base.runner.DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in base.runner.ACTIONS
)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_target_hue_redpink_brightness_v2_claims"
)
base.runner.DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_20260827_V2"
)

DIAGNOSTIC_OUTPUT_NAME = "j2-off-diagnostic.json"
ACTION_OUTPUT_NAMES = {
    1: "action-01-factory-otp-white-anchor.json",
    2: "action-02-source-columns.json",
    3: "action-03-middle-rows.json",
    4: "action-04-redpink-64-candidates.json",
    5: "action-05-redpink-repeat.json",
    6: "action-06-factory-otp-white-recovery.json",
}
DIAGNOSTIC_OUTPUT = base.runner.DEFAULT_OUTPUT / DIAGNOSTIC_OUTPUT_NAME
ACTION_OUTPUTS = {
    ordinal: base.runner.DEFAULT_OUTPUT / name
    for ordinal, name in ACTION_OUTPUT_NAMES.items()
}
Requester = Callable[..., tuple[int, Mapping[str, Any]]]
_MAX_JSON_BYTES = 16 * 1024 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FACTORY_WHITE_ANCHOR_ROLE = "FACTORY_OTP_WHITE_HEALTH_ANCHOR"


def _firmware_binding() -> dict[str, Any]:
    return {
        "bound": (
            _SHA256_RE.fullmatch(FIRMWARE_SHA256) is not None
            and FIRMWARE_BYTES > 0
            and _SHA256_RE.fullmatch(ELF_SHA256) is not None
            and ELF_BYTES > 0
        ),
        "bin": {"bytes": FIRMWARE_BYTES, "sha256": FIRMWARE_SHA256},
        "elf": {"bytes": ELF_BYTES, "sha256": ELF_SHA256},
    }


def _repo_relative(path: Path) -> str:
    return Path(path).relative_to(REPO_ROOT).as_posix()


def _fixed_cli_path(value: Path | None, expected: Path, *, label: str) -> Path:
    candidate = expected if value is None else Path(value)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    candidate = candidate.resolve()
    wanted = expected.resolve()
    if candidate != wanted:
        raise base.runner.RecheckError(
            f"{label} is fixed at {_repo_relative(expected)}"
        )
    return wanted


def _verify_local_artifacts() -> None:
    if not _firmware_binding()["bound"]:
        raise base.runner.RecheckError(
            "red/pink firmware binding is malformed; refusing device access"
        )
    for name, byte_count, sha256 in (
        ("firmware.bin", FIRMWARE_BYTES, FIRMWARE_SHA256),
        ("firmware.elf", ELF_BYTES, ELF_SHA256),
    ):
        artifact = BUILD_DIR / name
        if not artifact.is_file():
            raise base.runner.RecheckError(
                f"reviewed red/pink artifact is missing: {artifact}"
            )
        data = artifact.read_bytes()
        if len(data) != byte_count or hashlib.sha256(data).hexdigest() != sha256:
            raise base.runner.RecheckError(
                f"reviewed red/pink artifact identity differs: {artifact}"
            )


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    required_true = (
        "full_screen_global_refresh",
        "history_brightness_screening",
        "target_repeat_stability_probe",
        "busy_qualified_arm_execute_dispatch",
        "ordinal4_clear_visible_hit_required_for_repeat",
        "ordinal4_no_visible_difference_seals_main",
        "device_enforced_same_boot",
    )
    required_false = (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "command_0x86",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "same_palette_hold_probe",
        "cross_palette_hold_probe",
        "local_hold_claimed",
    )
    if any(value.get(key) is not True for key in required_true):
        raise base.runner.RecheckError("red/pink capability contract differs")
    if any(value.get(key) is not False for key in required_false):
        raise base.runner.RecheckError("red/pink forbidden capability contract differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="version")  # noqa: SLF001
    if value.get("layout_id") != pack.VARIANT_KEY:
        raise base.runner.RecheckError("red/pink layout identity differs")
    if value.get("action_count") != 6 or value.get("runtime_lut_write") is not True:
        raise base.runner.RecheckError("red/pink action/runtime contract differs")
    for key in (
        "automatic_execute",
        "automatic_chaining",
        "startup_refresh",
        "raw_frame_ingress",
        "electrical_parameter_write",
        "dither",
        "spatial_mixing",
        "retry",
        "recovery",
    ):
        if value.get(key) is not False:
            raise base.runner.RecheckError(f"red/pink safety {key} differs")
    if value.get("nvs_contract") != {
        "namespace": pack.NVS_NAMESPACE,
        "key": pack.NVS_KEY,
        "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
        "phases": {"READY": 0, "ARMED": 1, "CONSUMED": 2, "FAULT": 3},
        "initial_key_present": False,
        "initial_value": 1,
        "initial_next_ordinal": 1,
        "terminal_next_ordinal": 7,
        "campaign_boot_key": pack.NVS_BOOT_KEY,
        "campaign_boot_encoding": "uint64 high32_then_low32_hex_nonce",
        "campaign_boot_initial_key_present": False,
        "campaign_boot_initialize_only_when_cursor_key_absent_ready_ordinal1": True,
        "campaign_boot_readback_required": True,
        "current_boot_exact_match_required": True,
        "reboot_resume_allowed": False,
        "post_containment_resume_allowed": False,
    }:
        raise base.runner.RecheckError("red/pink NVS isolation differs")
    if value.get("baseline_contract") != {
        "ordinal": 1,
        "role": _FACTORY_WHITE_ANCHOR_ROLE,
        "external_anchor_required": False,
        "one_visible_refresh_required": True,
    }:
        raise base.runner.RecheckError("red/pink factory-white anchor differs")
    _validate_capabilities(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    exact = {
        "layout_id": pack.VARIANT_KEY,
        "actions": list(base.runner.ACTIONS),
        "action_count": 6,
        "one_driver_call_per_action": True,
        "factory_otp": True,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"red/pink manifest {key} differs")
    layout = value.get("history_layout", {})
    expected_layout = {
        "candidate_cells_per_controller": 64,
        "candidate_cells_total_observations": 128,
        "unique_recipes": 64,
        "duplicate_recipe_across_controllers": True,
        "controller_color_equivalence_claimed": False,
        "shared_red_or_pink_hue_claimed": False,
        "cs2_position_mirrored": False,
        "grid_rows": 8,
        "grid_columns_per_controller": 8,
        "row_axis": "commented_middle_code_0_to_7",
        "column_axis": "active_source_code_0_to_7",
        "target_hue_id": pack.TARGET_HUE_ID,
        "target_transport_code": pack.TARGET_CODE,
        "target_repeat_count": 2,
        "qualified_brightness_levels": 0,
        "brightness_candidates_only": True,
        "spatial_dither": False,
        "separator_gutter_history_interaction_qualified": False,
        "ptlw_command_issued": False,
        "cropped_dtm": False,
        "all_action_dtm_transport": "packed_frame_per_controller",
        "global_header_sequence": list(pack.GLOBAL_HEADERS),
        "same_boot_prior_complete_required": True,
        "device_enforced_same_boot": True,
        "campaign_boot_nonce_persisted_before_any_action": True,
        "campaign_boot_binding_key": pack.NVS_BOOT_KEY,
        "direct_exact_post_resume_after_reboot": False,
        "main_campaign_resume_after_containment": False,
        "skip_to_factory_white_allowed": False,
        "runtime_code7_used_as_white": False,
        "factory_otp_white_ordinals": [1, 6],
        "target_repeat_separate_manual_decision_action": True,
        "target_repeat_automatic_dispatch": False,
        "skip_target_repeat_within_main_allowed": False,
    }
    for key, wanted in expected_layout.items():
        if layout.get(key) != wanted:
            raise base.runner.RecheckError(f"red/pink history layout {key} differs")
    for key in (
        "cs1_r20_prefix_bytes",
        "cs1_r20_prefix_sha256",
        "cs2_r20_prefix_bytes",
        "cs2_r20_prefix_sha256",
        "r21_bytes",
        "r21_sha256",
    ):
        if layout.get(key) != REPORT["contract"]["profiles"]["active"][key]:
            raise base.runner.RecheckError(f"red/pink LUT {key} differs")
    _validate_capabilities(value)


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_busy: int
) -> str:
    ready_exact = {
        "state": "ready",
        "phase": 0,
        "phase_name": "READY",
        "cursor_raw": ordinal,
        "next_ordinal": ordinal,
        "current_action": None,
        "campaign_complete": False,
        "fixture_self_check_passed": True,
        "cursor_valid": True,
        "gpio_initialized": True,
        "execute_pending": False,
    }
    for key, wanted in ready_exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"red/pink V2 ready status {key} differs")
    if (
        not 1 <= ordinal <= 6
        or expected_busy not in (0, 1)
        or (expected_busy == 0 and ordinal != 1)
        or value.get("busy") != expected_busy
    ):
        raise base.runner.RecheckError(
            "red/pink every ordinal requires raw ready BUSY=1"
            if expected_busy == 1
            else "red/pink J2-OFF diagnostic requires ordinal 1 raw BUSY=0"
        )
    nonce = v1._BASE_VALIDATE_READY_STATUS(  # noqa: SLF001
        value, ordinal, expected_busy=expected_busy
    )
    for key in (
        "arm_request_count",
        "execute_request_count",
        "total_driver_call_count",
    ):
        if value.get(key) != ordinal - 1:
            raise base.runner.RecheckError(f"red/pink ready status {key} differs")
    if (
        value.get("campaign_boot_key_present") is not True
        or value.get("persisted_campaign_boot_nonce") != nonce
        or value.get("campaign_boot_matches_current") is not True
        or value.get("device_enforced_same_boot") is not True
        or value.get("reboot_resume_allowed") is not False
        or value.get("post_containment_resume_allowed") is not False
    ):
        raise base.runner.RecheckError(
            "red/pink persisted campaign boot binding differs"
        )
    return nonce


def _validate_prior_terminal_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    if ordinal <= 1:
        raise base.runner.RecheckError("red/pink prior ordinal differs")
    v3._validate_complete_report(value, ordinal - 1, boot_nonce)  # noqa: SLF001
    if ordinal == 2 and value.get("role") != _FACTORY_WHITE_ANCHOR_ROLE:
        raise base.runner.RecheckError(
            "red/pink ordinal 2 requires factory-OTP white anchor COMPLETE"
        )


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


def run_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: Any = None,
    poll_seconds: float = 65.0,
    poll_count: int = 60,
    visible_candidate_confirmed: bool = False,
) -> dict[str, Any]:
    if ordinal == 5 and not visible_candidate_confirmed:
        raise base.runner.RecheckError(
            "red/pink ordinal 5 requires an explicit visible candidate confirmation after ordinal 4"
        )
    if ordinal != 5 and visible_candidate_confirmed:
        raise base.runner.RecheckError(
            "red/pink visible candidate confirmation is valid only for ordinal 5"
        )
    _verify_local_artifacts()
    return v3.run_once(
        base_url,
        ordinal,
        claims=claims,
        output=output,
        requester=requester,
        poll_seconds=poll_seconds,
        poll_count=poll_count,
    )


def salvage_fault_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: Any = None,
) -> dict[str, Any]:
    _verify_local_artifacts()
    return v3.salvage_fault_once(
        base_url,
        ordinal,
        claims=claims,
        output=output,
        requester=requester,
    )


def describe() -> dict[str, Any]:
    value = deepcopy(v3.describe())
    value["offline_description_only"] = True
    value["network_requests"] = 0
    value["visible_refreshes"] = 0
    value["device_network_accessed"] = False
    value["serial_or_com_accessed"] = False
    value["relay_accessed"] = False
    value["firmware_flashed"] = False
    value["display_refreshed"] = False
    value["variant"] = deepcopy(REPORT["contract"])
    value["firmware_binding"] = _firmware_binding()
    value["artifact_preflight_required_before_device_access"] = True
    value["successor_isolation"] = {
        "v1_namespace_reused": False,
        "v1_cursor_key_reused": False,
        "v1_boot_key_reused": False,
        "v1_routes_reused": False,
        "v1_claims_root_reused": False,
        "v1_output_root_reused": False,
        "fresh_v2_namespace": pack.NVS_NAMESPACE,
        "fresh_v2_cursor_key": pack.NVS_KEY,
        "fresh_v2_boot_key": pack.NVS_BOOT_KEY,
    }
    value["single_app_boot_flash_verify_contract"] = {
        "application_offset": "0x10000",
        "write_flash_after": "no_reset",
        "verify_flash_before": "no_reset",
        "verify_flash_after": "hard_reset",
        "application_boots_between_write_and_verify": 0,
        "first_application_boot_after_verify": True,
        "no_extra_reset_or_chip_id_or_monitor_before_diagnostic": True,
    }
    value["diagnose_j2_off"] = {
        "artifact_preflight_before_network": True,
        "base_url": "private_or_local_literal_ipv4_http_only",
        "proxy": False,
        "redirect": False,
        "network": {"get": 4, "post": 0},
        "permanent_claims_created": 0,
        "visible_refreshes": 0,
        "output_write_contract": "O_EXCL",
    }
    value["fixed_output_files"] = {
        "root": _repo_relative(base.runner.DEFAULT_OUTPUT),
        "diagnostic": _repo_relative(DIAGNOSTIC_OUTPUT),
        "actions": {
            str(ordinal): _repo_relative(path)
            for ordinal, path in ACTION_OUTPUTS.items()
        },
        "claims_root": _repo_relative(base.runner.DEFAULT_CLAIMS),
    }
    value["preflight_busy_contract"] = {
        "ordinals_1_to_6": "RAW_READY_BUSY_1_ONLY",
        "busy_zero_accepted": False,
        "firmware_gates": ["ARM", "EXECUTE", "DISPATCH"],
    }
    value["fixed_transport"] = {
        "spi_hz": 1_000_000,
        "runtime_lut": True,
        "profile_sequence": list(pack.GLOBAL_HEADERS),
        "packed_full_frame_per_controller": True,
        "ptlw_command_issued": False,
        "partial_refresh": False,
        "spatial_dither": False,
        "target_hue_id": pack.TARGET_HUE_ID,
        "target_code": pack.TARGET_CODE,
        "candidate_recipes": 64,
        "physical_observations": 128,
        "qualified_brightness_levels": 0,
        "blocking_refresh_first_poll_floor_seconds": 65.0,
    }
    value["ordinal_progression"] = {
        "strict_same_boot_prior_complete_required": True,
        "device_enforced_same_boot": True,
        "persisted_campaign_boot_key": pack.NVS_BOOT_KEY,
        "direct_exact_post_resume_after_reboot": False,
        "main_campaign_resume_after_containment": False,
        "skip_to_factory_white_recovery": False,
        "ordinal_6_requires_ordinal_5_complete": True,
        "ordinal_5_target_repeat_requires_fresh_operator_decision": True,
        "ordinal_5_automatic_dispatch": False,
        "ordinal_5_host_confirmation_flag": (
            "--confirm-visible-candidate-after-ordinal4"
        ),
    }
    value["ordinal4_fast_gate"] = deepcopy(REPORT["contract"]["ordinal4_fast_gate"])
    value["evidence_boundary"] = {
        "brightness_candidates_not_levels": True,
        "controller_repeats_not_additional_unique_colours": True,
        "controller_colour_equivalence_not_claimed": True,
        "separator_gutters_not_measurement_regions": True,
        "local_hold_not_tested_or_claimed": True,
    }
    return value


def _diagnostic_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _diagnostic_origin(value: str) -> str:
    """Accept only an exact RFC1918, loopback, or link-local IPv4 origin."""

    if not isinstance(value, str):
        raise base.runner.RecheckError(
            "diagnose base URL must be a private/local literal IPv4 HTTP origin"
        )
    parsed = urllib_parse.urlsplit(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise base.runner.RecheckError("diagnose base URL port is invalid") from error
    if (
        parsed.scheme != "http"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.netloc.endswith(":")
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise base.runner.RecheckError(
            "diagnose base URL must be an exact plain HTTP origin"
        )
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError as error:
        raise base.runner.RecheckError(
            "diagnose base URL must use a literal IPv4 address"
        ) from error
    rfc1918 = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
    )
    if address.version != 4 or not (
        any(address in network for network in rfc1918)
        or address.is_loopback
        or address.is_link_local
    ):
        raise base.runner.RecheckError(
            "diagnose base URL must use a private/local literal IPv4 address"
        )
    authority = str(address) if port is None else f"{address}:{port}"
    return f"http://{authority}"


def _diagnostic_timeout(value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0 < float(value) <= 30
    ):
        raise base.runner.RecheckError("diagnose timeout must be in (0,30]")
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


def _diagnostic_http_request(
    base_url: str,
    path: str,
    *,
    method: str,
    headers: Mapping[str, str] | None,
    timeout: float,
) -> tuple[int, Mapping[str, Any]]:
    """Perform one direct request with proxies and redirects disabled."""

    request = urllib_request.Request(
        base_url + path,
        method=method,
        headers={"Accept": "application/json", **dict(headers or {})},
    )
    opener = urllib_request.build_opener(urllib_request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:  # noqa: S310
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


def _diagnostic_get(
    requester: Requester,
    transcript: list[dict[str, Any]],
    origin: str,
    endpoint: str,
    *,
    timeout: float,
) -> Mapping[str, Any]:
    entry: dict[str, Any] = {
        "method": "GET",
        "endpoint": endpoint,
        "path": base.runner.ENDPOINTS[endpoint],
        "headers": {},
    }
    transcript.append(entry)
    try:
        response = requester(
            origin,
            base.runner.ENDPOINTS[endpoint],
            method="GET",
            headers=None,
            timeout=timeout,
        )
    except Exception as error:
        entry["transport_error"] = f"{type(error).__name__}: {error}"
        raise base.runner.RecheckError(f"GET {endpoint} failed: {error}") from error
    if not isinstance(response, tuple) or len(response) != 2:
        entry["response_error"] = "requester did not return (status, object)"
        raise base.runner.RecheckError(f"GET {endpoint} returned malformed data")
    status, value = response
    entry["status"] = status
    if isinstance(value, Mapping):
        entry["response"] = deepcopy(dict(value))
    else:
        entry["response_error"] = f"root type is {type(value).__name__}"
    if isinstance(status, bool) or not isinstance(status, int):
        raise base.runner.RecheckError(f"GET {endpoint} returned malformed status")
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError(f"GET {endpoint} response root is not an object")
    if status != 200:
        raise base.runner.RecheckError(f"GET {endpoint} returned HTTP {status}")
    return value


def _diagnostic_network_counts(
    transcript: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    return {
        "get": sum(item.get("method") == "GET" for item in transcript),
        "post": sum(item.get("method") == "POST" for item in transcript),
    }


def diagnose_j2_off(
    base_url: str,
    *,
    output: Path,
    confirm_j2_off: bool = False,
    requester: Requester | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Seal an artifact-first four-GET fresh-state check with zero mutation."""

    if confirm_j2_off is not True:
        raise base.runner.RecheckError(
            "red/pink V2 diagnose-j2-off requires explicit J2-OFF confirmation"
        )
    output = Path(output)
    if output.exists():
        raise base.runner.RecheckError(f"refusing to overwrite {output}")
    transcript: list[dict[str, Any]] = []
    artifact_preflight_complete = False
    origin: str | None = None
    try:
        # This gate remains before origin selection and before the first
        # requester call, while still allowing a zero-request failure record.
        _verify_local_artifacts()
        artifact_preflight_complete = True
        origin = _diagnostic_origin(base_url)
        checked_timeout = _diagnostic_timeout(timeout)
        selected_requester = requester or _diagnostic_http_request
        observed = {
            endpoint: _diagnostic_get(
                selected_requester,
                transcript,
                origin,
                endpoint,
                timeout=checked_timeout,
            )
            for endpoint in ("version", "manifest", "status", "report")
        }
        _validate_version(observed["version"])
        _validate_manifest(observed["manifest"])
        boot_nonce = _validate_ready_status(observed["status"], 1, expected_busy=0)
        v1._validate_fresh_no_execute_report(  # noqa: SLF001
            observed["report"], boot_nonce
        )
        evidence = base.runner._seal(  # noqa: SLF001
            {
                "schema_version": 1,
                "kind": (f"{base.runner.EVIDENCE_KIND_PREFIX}-j2-off-diagnostic"),
                "created_at": _diagnostic_now(),
                "outcome": "j2_off_diagnostic_pass",
                "build_tag": pack.BUILD_TAG,
                "test_id": pack.TEST_ID,
                "campaign_id": pack.CAMPAIGN_ID,
                "contract_id": REPORT["contract_id"],
                "local_artifact_binding": _firmware_binding(),
                "artifact_preflight_completed_before_network": True,
                "base_url": origin,
                "transport": {
                    "mode": "direct_private_literal_ipv4_http",
                    "proxy": False,
                    "redirect": False,
                },
                "boot_nonce": boot_nonce,
                "j2_confirmed_off": True,
                "next_ordinal": 1,
                "fresh_cursor_key_absent": True,
                "campaign_boot_key_present_and_current": True,
                "status": deepcopy(dict(observed["status"])),
                "report": deepcopy(dict(observed["report"])),
                "transcript": transcript,
                "network": _diagnostic_network_counts(transcript),
                "permanent_claims_created": 0,
                "claims_directory_accessed": False,
                "visible_refreshes": 0,
                "output_write_contract": "O_EXCL",
                "no_retry": True,
                "no_recovery": True,
                "no_autochain": True,
            }
        )
        base.runner._write_new(output, evidence)  # noqa: SLF001
        return evidence
    except Exception as error:
        if not output.exists():
            attempt = base.runner._seal(  # noqa: SLF001
                {
                    "schema_version": 1,
                    "kind": (
                        f"{base.runner.EVIDENCE_KIND_PREFIX}-j2-off-diagnostic-attempt"
                    ),
                    "created_at": _diagnostic_now(),
                    "outcome": "j2_off_diagnostic_failed_no_claim",
                    "build_tag": pack.BUILD_TAG,
                    "campaign_id": pack.CAMPAIGN_ID,
                    "contract_id": REPORT["contract_id"],
                    "local_artifact_binding": _firmware_binding(),
                    "artifact_preflight_completed_before_network": (
                        artifact_preflight_complete
                    ),
                    "base_url": origin,
                    "transport": {
                        "mode": "direct_private_literal_ipv4_http",
                        "proxy": False,
                        "redirect": False,
                    },
                    "error": {
                        "type": type(error).__name__,
                        "message": str(error),
                    },
                    "j2_confirmed_off": True,
                    "transcript": transcript,
                    "network": _diagnostic_network_counts(transcript),
                    "permanent_claims_created": 0,
                    "claims_directory_accessed": False,
                    "visible_refreshes": 0,
                    "output_write_contract": "O_EXCL",
                    "no_retry": True,
                    "no_recovery": True,
                    "no_autochain": True,
                }
            )
            try:
                base.runner._write_new(output, attempt)  # noqa: SLF001
            except Exception as write_error:
                raise base.runner.RecheckError(
                    f"red/pink V2 J2-OFF diagnostic failed: {error}; "
                    f"attempt evidence write failed: {write_error}"
                ) from error
        if isinstance(error, base.runner.RecheckError):
            raise
        raise base.runner.RecheckError(
            f"red/pink V2 J2-OFF diagnostic failed: {error}"
        ) from error


def dry_validate() -> dict[str, Any]:
    """Verify frozen local artifacts and campaign identities without I/O."""

    _verify_local_artifacts()
    report = pack.build_report()
    contract = report["contract"]
    actions = report["actions"]
    expected_roles = (
        "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "REDPINK_SOURCE_GRID_ACTIVE",
        "REDPINK_MIDDLE_GRID_COMMENTED",
        "REDPINK_FIXED_TARGET_ACTIVE_CODE0",
        "REDPINK_FIXED_TARGET_REPEAT_ACTIVE_CODE0",
        "FACTORY_OTP_WHITE_RECOVERY",
    )
    if report["contract_id"] != base.runner.CONTRACT_ID:
        raise base.runner.RecheckError("red/pink offline contract identity differs")
    if tuple(item["role"] for item in actions) != expected_roles:
        raise base.runner.RecheckError("red/pink offline action sequence differs")
    if tuple(item["action_id"] for item in actions) != base.runner.ACTION_IDS:
        raise base.runner.RecheckError("red/pink offline action identities differ")
    if (
        len(contract["recipes"]) != 64
        or contract["geometry"]["candidate_cells_per_controller"] != 64
        or contract["geometry"]["candidate_cells_total_observations"] != 128
        or contract["geometry"]["spatial_dither"] is not False
        or contract["target_hue_registry"]["target_transport_code"] != 0
        or contract["target_hue_registry"]["selection_not_guess"] is not True
        or contract["factory_otp_white"]["ordinals"] != [1, 6]
        or contract["factory_otp_white"]["runtime_code7_used_as_white"] is not False
        or contract["target_repeat_decision"]["automatic_dispatch"] is not False
        or contract["strict_ordinal_progression"]["action6_requires_action5_complete"]
        is not True
        or contract["strict_ordinal_progression"]["device_enforced_same_boot"]
        is not True
        or contract["strict_ordinal_progression"][
            "direct_exact_post_resume_after_reboot"
        ]
        is not False
        or contract["strict_ordinal_progression"][
            "main_campaign_resume_after_containment"
        ]
        is not False
        or contract["ordinal4_fast_gate"]["if_no_visible_difference"]["arm_ordinal5"]
        is not False
    ):
        raise base.runner.RecheckError("red/pink offline campaign invariant differs")
    return {
        "kind": "mf1750-ec5-target-hue-redpink-brightness-v2-dry-validation",
        "result": "PASS",
        "offline_only": True,
        "device_requests_made": 0,
        "network_requests": 0,
        "visible_refreshes": 0,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "build_tag": pack.BUILD_TAG,
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": report["contract_id"],
        "target_hue_catalog_id": pack.TARGET_HUE_CATALOG_ID,
        "target_transport_code": pack.TARGET_CODE,
        "unique_recipes": len(contract["recipes"]),
        "physical_observations": contract["geometry"][
            "candidate_cells_total_observations"
        ],
        "action_ids": [item["action_id"] for item in actions],
        "firmware_binding": _firmware_binding(),
        "target_repeat": {
            "ordinal": 5,
            "separate_operator_decision": True,
            "automatic_dispatch": False,
            "skip_to_recovery_allowed": False,
            "visible_candidate_confirmation_after_ordinal4_required": True,
        },
        "same_boot_binding": deepcopy(contract["boot_session_admission"]),
        "ordinal4_fast_gate": deepcopy(contract["ordinal4_fast_gate"]),
        "successor_isolation": {
            "v1_namespace_reused": False,
            "namespace": pack.NVS_NAMESPACE,
            "cursor_key": pack.NVS_KEY,
            "boot_key": pack.NVS_BOOT_KEY,
        },
        "diagnose_j2_off": {
            "artifact_preflight_before_network": True,
            "network": {"get": 4, "post": 0},
            "permanent_claims_created": 0,
            "visible_refreshes": 0,
            "output_write_contract": "O_EXCL",
            "private_literal_ipv4": True,
            "proxy": False,
            "redirect": False,
        },
        "fixed_output_files": {
            "diagnostic": _repo_relative(DIAGNOSTIC_OUTPUT),
            "actions": {
                str(ordinal): _repo_relative(path)
                for ordinal, path in ACTION_OUTPUTS.items()
            },
        },
        "single_app_boot_flash_verify_contract": {
            "write_flash_after": "no_reset",
            "verify_flash_before": "no_reset",
            "verify_flash_after": "hard_reset",
            "application_boots_between_write_and_verify": 0,
            "first_application_boot_after_verify": True,
        },
    }


# Rebind all dynamic points in the isolated host stack.
v3._validate_capabilities = _validate_capabilities
v3._validate_version = _validate_version
v3._validate_manifest = _validate_manifest
v3._validate_ready_status = _validate_ready_status
v3._validate_prior_terminal_report = _validate_prior_terminal_report
v3._preflight = _preflight
base._validate_capabilities = _validate_capabilities
base._validate_version = _validate_version
base._validate_manifest = _validate_manifest
base.runner._validate_version = _validate_version
base.runner._validate_manifest = _validate_manifest
base.runner._validate_ready_status = _validate_ready_status
base.runner._preflight = _preflight
base.runner.run_once = run_once
base.runner.describe = describe
v1._validate_version = _validate_version
v1._validate_manifest = _validate_manifest
v1._preflight = _preflight


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    sub.add_parser("dry-validate")
    diagnostic = sub.add_parser("diagnose-j2-off", allow_abbrev=False)
    diagnostic.add_argument("--base-url", required=True)
    diagnostic.add_argument("--confirm-j2-off", action="store_true", required=True)
    diagnostic.add_argument("--output", type=Path)
    diagnostic.add_argument("--timeout", type=float, default=10.0)
    run = sub.add_parser("run", allow_abbrev=False)
    run.add_argument("--base-url", required=True)
    run.add_argument("--ordinal", type=int, required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument(
        "--confirm-visible-candidate-after-ordinal4",
        action="store_true",
        help="required only for ordinal 5 after a clear visible hit at ordinal 4",
    )
    run.add_argument("--claims", type=Path, default=base.runner.DEFAULT_CLAIMS)
    run.add_argument("--output", type=Path)
    run.add_argument("--poll-seconds", type=float, default=65.0)
    run.add_argument("--poll-count", type=int, default=60)
    salvage = sub.add_parser("salvage-fault")
    salvage.add_argument("--base-url", required=True)
    salvage.add_argument("--ordinal", type=int, required=True)
    salvage.add_argument("--claims", type=Path, default=base.runner.DEFAULT_CLAIMS)
    salvage.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "describe":
            value = describe()
        elif args.command == "dry-validate":
            value = dry_validate()
        elif args.command == "diagnose-j2-off":
            value = diagnose_j2_off(
                args.base_url,
                output=_fixed_cli_path(
                    args.output,
                    DIAGNOSTIC_OUTPUT,
                    label="diagnostic output",
                ),
                confirm_j2_off=args.confirm_j2_off,
                timeout=args.timeout,
            )
        elif args.command == "salvage-fault":
            value = salvage_fault_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output,
            )
        else:
            expected_output = ACTION_OUTPUTS.get(args.ordinal)
            if expected_output is None:
                raise base.runner.RecheckError("ordinal must be between 1 and 6")
            value = run_once(
                args.base_url,
                args.ordinal,
                claims=_fixed_cli_path(
                    args.claims,
                    base.runner.DEFAULT_CLAIMS,
                    label="claims root",
                ),
                output=_fixed_cli_path(
                    args.output,
                    expected_output,
                    label=f"ordinal {args.ordinal} output",
                ),
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
                visible_candidate_confirmed=(
                    args.confirm_visible_candidate_after_ordinal4
                ),
            )
    except base.runner.RecheckError as error:
        print(f"red/pink brightness candidate V2 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
