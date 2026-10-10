#!/usr/bin/env python3
"""Fail-closed one-action runner for the four-step same-R20 parity probe.

This runner never flashes, resets, controls J2/power, retries, recovers, or
autochains.  It verifies the reviewed local BIN/ELF before any device request,
requires raw BUSY=1 for every ordinal, and accepts only strict terminal BUSY
evidence.  Each invocation can consume exactly one of four immutable actions;
it never retries, recovers, skips, or automatically dispatches the next one.
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

from tools import mf1750_runtime_lut_same_r20_parity_v1_pack as pack  # noqa: E402


_V3_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_same_r20_parity_v1_private_v3_host", _V3_PATH
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
base.runner.DEVICE_API_VERSION = pack.DEVICE_API_VERSION
base.runner.IDENTITY_REVISION = pack.IDENTITY_REVISION
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = pack.CLASSIFICATION
base.runner.DEVICE_KIND_PREFIX = "mf1750-ec5-same-r20-parity-v1"
base.runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-same-r20-parity-v1"
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY

FIRMWARE_SHA256 = "d65fb20b3e3843563561340d6bb450fc469ade4e503fec87eec3f0369e30977f"
FIRMWARE_BYTES = 801_712
ELF_SHA256 = "bf15d35d12af897d89afd2ab65141a50dd3dc4e2350877abc3ada530f8de94b6"
ELF_BYTES = 13_299_408
BUILD_DIR = (
    REPO_ROOT
    / ".pio"
    / "build-runtime-lut-same-r20-parity-v1"
    / "ec5_runtime_lut_same_r20_parity_v1"
)
base.runner.FIRMWARE_SHA256 = FIRMWARE_SHA256
base.runner.FIRMWARE_BYTES = FIRMWARE_BYTES
base.runner.ENDPOINTS = {
    name: f"{pack.BASE_ROUTE}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = (
    "ARM_ONE_FIXED_SAME_R20_PARITY_ACTION_NOT_HARDWARE_AUTHORIZATION"
)
base.runner.EXECUTE_INTENT = "EXECUTE_ONE_ARMED_SAME_R20_PARITY_ACTION_ONCE"


def _actions() -> tuple[dict[str, Any], ...]:
    """Match the exact action-object shape emitted by this firmware."""

    actions = deepcopy(base._actions())
    contract_actions = REPORT["contract"]["actions"]
    if len(actions) != len(contract_actions):
        raise base.runner.RecheckError("same-R20 parity action table length differs")
    for action, contract_action in zip(actions, contract_actions, strict=True):
        factory_otp = contract_action["palette_source"] == "FACTORY_OTP"
        action["palette_source"] = contract_action["palette_source"]
        action["global_header"] = contract_action["global_header"]
        action["profile_id"] = contract_action["profile_id"]
        action["global_tuple_id"] = contract_action["global_tuple_id"]
        action["waveform_binding"] = deepcopy(contract_action["waveform_binding"])
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
    REPO_ROOT / ".test-output" / "hardware" / ".mf1750_same_r20_parity_v1_claims"
)
base.runner.DEFAULT_OUTPUT = (
    REPO_ROOT / ".test-output" / "hardware" / "MF1750_SAME_R20_PARITY_20260828_V1"
)

DIAGNOSTIC_OUTPUT_NAME = "j2-off-diagnostic.json"
ACTION_OUTPUT_NAMES = {
    1: "action-01-active-active-atlas.json",
    2: "action-02-factory-otp-white-after-aa.json",
    3: "action-03-commented-commented-atlas.json",
    4: "action-04-factory-otp-white-after-cc.json",
}
DIAGNOSTIC_OUTPUT = base.runner.DEFAULT_OUTPUT / DIAGNOSTIC_OUTPUT_NAME
ACTION_OUTPUTS = {
    ordinal: base.runner.DEFAULT_OUTPUT / name
    for ordinal, name in ACTION_OUTPUT_NAMES.items()
}
Requester = Callable[..., tuple[int, Mapping[str, Any]]]
_MAX_JSON_BYTES = 16 * 1024 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FACTORY_WHITE_ANCHOR_ROLE = "V3_FACTORY_OTP_WHITE_SUCCESSOR_REQUIRED_BEFORE_CAMPAIGN"


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
            "same-R20 parity firmware binding is malformed; refusing device access"
        )
    for name, byte_count, sha256 in (
        ("firmware.bin", FIRMWARE_BYTES, FIRMWARE_SHA256),
        ("firmware.elf", ELF_BYTES, ELF_SHA256),
    ):
        artifact = BUILD_DIR / name
        if not artifact.is_file():
            raise base.runner.RecheckError(
                f"reviewed same-R20 parity artifact is missing: {artifact}"
            )
        data = artifact.read_bytes()
        if len(data) != byte_count or hashlib.sha256(data).hexdigest() != sha256:
            raise base.runner.RecheckError(
                f"reviewed same-R20 parity artifact identity differs: {artifact}"
            )


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    required_true = (
        "full_screen_global_refresh",
        "same_r20_controller_parity_probe",
        "busy_qualified_arm_execute_dispatch",
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
        "colour_qualification",
    )
    if any(value.get(key) is not True for key in required_true):
        raise base.runner.RecheckError("same-R20 parity capability contract differs")
    if any(value.get(key) is not False for key in required_false):
        raise base.runner.RecheckError(
            "same-R20 parity forbidden capability contract differs"
        )


def _validate_version(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="version")  # noqa: SLF001
    if value.get("layout_id") != pack.VARIANT_KEY:
        raise base.runner.RecheckError("same-R20 parity layout identity differs")
    if value.get("action_count") != 4 or value.get("runtime_lut_write") is not True:
        raise base.runner.RecheckError(
            "same-R20 parity action/runtime contract differs"
        )
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
            raise base.runner.RecheckError(f"same-R20 parity safety {key} differs")
    if value.get("nvs_contract") != {
        "namespace": pack.NVS_NAMESPACE,
        "key": pack.NVS_KEY,
        "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
        "phases": {"READY": 0, "ARMED": 1, "CONSUMED": 2, "FAULT": 3},
        "initial_key_present": False,
        "initial_value": 1,
        "initial_next_ordinal": 1,
        "terminal_next_ordinal": 5,
        "campaign_boot_key": pack.NVS_BOOT_KEY,
        "campaign_boot_encoding": "uint64 high32_then_low32_hex_nonce",
        "campaign_boot_initial_key_present": False,
        "campaign_boot_initialize_only_when_cursor_key_absent_ready_ordinal1": True,
        "campaign_boot_readback_required": True,
        "current_boot_exact_match_required": True,
        "reboot_resume_allowed": False,
        "post_containment_resume_allowed": False,
    }:
        raise base.runner.RecheckError("same-R20 parity NVS isolation differs")
    if value.get("baseline_contract") != {
        "ordinal": None,
        "role": _FACTORY_WHITE_ANCHOR_ROLE,
        "external_anchor_required": True,
        "one_visible_refresh_required": False,
    }:
        raise base.runner.RecheckError("same-R20 parity factory-white anchor differs")
    if value.get("external_white_anchor") != pack.EXTERNAL_WHITE_ANCHOR:
        raise base.runner.RecheckError("same-R20 parity external white binding differs")
    _validate_capabilities(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    exact = {
        "layout_id": pack.VARIANT_KEY,
        "actions": list(base.runner.ACTIONS),
        "action_count": 4,
        "one_driver_call_per_action": True,
        "factory_otp": True,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"same-R20 parity manifest {key} differs")
    if value.get("external_white_anchor") != pack.EXTERNAL_WHITE_ANCHOR:
        raise base.runner.RecheckError(
            "same-R20 parity manifest external white differs"
        )
    layout = value.get("history_layout", {})
    expected_layout = {
        "controller_count": 2,
        "controller_width": 512,
        "height": 600,
        "cs2_position_mirrored": False,
        "grid_rows": 2,
        "grid_columns_per_controller": 4,
        "codes": list(range(8)),
        "grid_x0_local": 40,
        "grid_y0": 120,
        "grid_x1_local_exclusive": 484,
        "grid_y1_exclusive": 400,
        "cell_width": 96,
        "cell_height": 120,
        "gap_x": 20,
        "gap_y": 40,
        "same_layout_both_controllers": True,
        "controller_dtm_byte_identical": True,
        "spatial_dither": False,
        "factory_otp_white_ordinals": [2, 4],
        "runtime_lut_ordinals": [1, 3],
        "one_visible_refresh_per_action": True,
        "qualified_colours": 0,
        "colour_equivalence_claimed": False,
        "controller_bus_capture_claimed": False,
        "active_global_tuple_id": REPORT["contract"]["profiles"]["active"][
            "global_tuple_id"
        ],
        "commented_global_tuple_id": REPORT["contract"]["profiles"]["commented"][
            "global_tuple_id"
        ],
    }
    for key, wanted in expected_layout.items():
        if layout.get(key) != wanted:
            raise base.runner.RecheckError(
                f"same-R20 parity history layout {key} differs"
            )
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
            raise base.runner.RecheckError(
                f"same-R20 parity ready status {key} differs"
            )
    if (
        not 1 <= ordinal <= 4
        or expected_busy not in (0, 1)
        or (expected_busy == 0 and ordinal != 1)
        or value.get("busy") != expected_busy
    ):
        raise base.runner.RecheckError(
            "same-R20 parity every ordinal requires raw ready BUSY=1"
            if expected_busy == 1
            else "same-R20 parity J2-OFF diagnostic requires ordinal 1 raw BUSY=0"
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
            raise base.runner.RecheckError(
                f"same-R20 parity ready status {key} differs"
            )
    if (
        value.get("campaign_boot_key_present") is not True
        or value.get("persisted_campaign_boot_nonce") != nonce
        or value.get("campaign_boot_matches_current") is not True
        or value.get("device_enforced_same_boot") is not True
        or value.get("reboot_resume_allowed") is not False
        or value.get("post_containment_resume_allowed") is not False
    ):
        raise base.runner.RecheckError(
            "same-R20 parity persisted campaign boot binding differs"
        )
    return nonce


def _validate_prior_terminal_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    if ordinal <= 1:
        raise base.runner.RecheckError("same-R20 parity prior ordinal differs")
    v3._validate_complete_report(value, ordinal - 1, boot_nonce)  # noqa: SLF001
    expected_role = pack.ROLES[ordinal - 2]
    if value.get("role") != expected_role:
        raise base.runner.RecheckError("same-R20 parity prior role differs")


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


def _verify_external_white_anchor() -> None:
    """Require the independent V3 white successor before ordinal 1 I/O."""

    binding = pack.EXTERNAL_WHITE_ANCHOR
    path = REPO_ROOT / binding["evidence_path"]
    if not path.is_file() or path.is_symlink():
        raise base.runner.RecheckError(
            "independent V3 factory-white anchor evidence is missing"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise base.runner.RecheckError(
            "independent V3 factory-white anchor evidence is invalid"
        ) from error
    if not isinstance(value, Mapping) or not isinstance(
        value.get("integrity"), Mapping
    ):
        raise base.runner.RecheckError("V3 factory-white anchor integrity is missing")
    body = dict(value)
    integrity = body.pop("integrity")
    observed = hashlib.sha256(pack._canonical(body)).hexdigest()  # noqa: SLF001
    if (
        integrity.get("algorithm") != "sha256-canonical-json-without-integrity"
        or integrity.get("sha256") != observed
    ):
        raise base.runner.RecheckError("V3 factory-white anchor integrity differs")
    action = value.get("action")
    expected = {
        "outcome": binding["required_outcome"],
        "firmware_sha256": binding["firmware_bin_sha256"],
        "running_app_elf_sha256": binding["firmware_elf_sha256"],
        "visible_refreshes": 1,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "no_ordinal_skip": True,
    }
    if any(value.get(key) != wanted for key, wanted in expected.items()):
        raise base.runner.RecheckError("V3 factory-white anchor result differs")
    if (
        not isinstance(action, Mapping)
        or action.get("action_id") != binding["action_id"]
    ):
        raise base.runner.RecheckError("V3 factory-white anchor action differs")
    terminal = value.get("terminal_report")
    if (
        not isinstance(terminal, Mapping)
        or terminal.get("terminal_state") != "COMPLETE"
    ):
        raise base.runner.RecheckError("V3 factory-white anchor is not COMPLETE")


def run_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: Any = None,
    poll_seconds: float = 65.0,
    poll_count: int = 60,
) -> dict[str, Any]:
    _verify_local_artifacts()
    if ordinal == 1:
        _verify_external_white_anchor()
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
        "fresh_v1_namespace": pack.NVS_NAMESPACE,
        "fresh_v1_cursor_key": pack.NVS_KEY,
        "fresh_v1_boot_key": pack.NVS_BOOT_KEY,
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
        "ordinals_1_to_4": "RAW_READY_BUSY_1_ONLY",
        "busy_zero_accepted": False,
        "firmware_gates": ["ARM", "EXECUTE", "DISPATCH"],
    }
    value["fixed_transport"] = {
        "spi_hz": 1_000_000,
        "runtime_lut": True,
        "profile_sequence": ["active", None, "commented", None],
        "packed_full_frame_per_controller": True,
        "ptlw_command_issued": False,
        "partial_refresh": False,
        "spatial_dither": False,
        "atlas_codes": list(range(8)),
        "cells_per_controller": 8,
        "controller_dtm_byte_identical": True,
        "qualified_colours": 0,
        "blocking_refresh_first_poll_floor_seconds": 65.0,
    }
    value["ordinal_progression"] = {
        "strict_same_boot_prior_complete_required": True,
        "device_enforced_same_boot": True,
        "persisted_campaign_boot_key": pack.NVS_BOOT_KEY,
        "direct_exact_post_resume_after_reboot": False,
        "main_campaign_resume_after_containment": False,
        "skip_to_factory_white_recovery": False,
        "four_actions_independent": True,
        "one_visible_refresh_per_action": True,
    }
    value["external_white_anchor"] = deepcopy(pack.EXTERNAL_WHITE_ANCHOR)
    value["evidence_boundary"] = {
        "controller_colour_equivalence_not_claimed": True,
        "compiled_payload_source_identity_not_bus_capture": True,
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
            "same-R20 parity diagnose-j2-off requires explicit J2-OFF confirmation"
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
                    f"same-R20 parity J2-OFF diagnostic failed: {error}; "
                    f"attempt evidence write failed: {write_error}"
                ) from error
        if isinstance(error, base.runner.RecheckError):
            raise
        raise base.runner.RecheckError(
            f"same-R20 parity J2-OFF diagnostic failed: {error}"
        ) from error


def dry_validate() -> dict[str, Any]:
    """Verify frozen local artifacts and campaign identities without I/O."""

    _verify_local_artifacts()
    report = pack.build_report()
    contract = report["contract"]
    actions = report["actions"]
    expected_roles = (
        "SAME_R20_ACTIVE_ACTIVE_ATLAS",
        "FACTORY_OTP_WHITE_AFTER_ACTIVE_ACTIVE",
        "SAME_R20_COMMENTED_COMMENTED_ATLAS",
        "FACTORY_OTP_WHITE_AFTER_COMMENTED_COMMENTED",
    )
    if report["contract_id"] != base.runner.CONTRACT_ID:
        raise base.runner.RecheckError(
            "same-R20 parity offline contract identity differs"
        )
    if tuple(item["role"] for item in actions) != expected_roles:
        raise base.runner.RecheckError(
            "same-R20 parity offline action sequence differs"
        )
    if tuple(item["action_id"] for item in actions) != base.runner.ACTION_IDS:
        raise base.runner.RecheckError(
            "same-R20 parity offline action identities differ"
        )
    if (
        contract["action_count"] != 4
        or contract["geometry"]["grid_rows"] != 2
        or contract["geometry"]["grid_columns_per_controller"] != 4
        or contract["geometry"]["codes"] != list(range(8))
        or contract["geometry"]["same_layout_both_controllers"] is not True
        or contract["geometry"]["spatial_dither"] is not False
        or contract["factory_otp_white_ordinals"] != [2, 4]
        or contract["runtime_lut_ordinals"] != [1, 3]
        or contract["one_visible_refresh_per_action"] is not True
        or contract["automatic_chaining"] is not False
        or contract["retry"] is not False
        or contract["recovery"] is not False
        or actions[0]["cs1_dtm"] != actions[0]["cs2_dtm"]
        or actions[2]["cs1_dtm"] != actions[2]["cs2_dtm"]
        or actions[0]["cs1_dtm"] != actions[2]["cs1_dtm"]
        or actions[0]["frame"] != actions[2]["frame"]
    ):
        raise base.runner.RecheckError(
            "same-R20 parity offline campaign invariant differs"
        )
    for name in ("active", "commented"):
        profile = contract["profiles"][name]
        if (
            profile["cs1"] != profile["cs2"]
            or profile["controller_payloads_byte_identical"] is not True
            or profile["global_tuple_id"]
            != actions[0 if name == "active" else 2]["global_tuple_id"]
        ):
            raise base.runner.RecheckError(
                f"same-R20 parity {name} symmetric tuple differs"
            )
    return {
        "kind": "mf1750-ec5-same-r20-parity-v1-dry-validation",
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
        "atlas_codes": list(range(8)),
        "cells_per_controller": 8,
        "controller_dtm_byte_identical": True,
        "action_ids": [item["action_id"] for item in actions],
        "firmware_binding": _firmware_binding(),
        "profile_bindings": deepcopy(contract["profiles"]),
        "external_white_anchor": deepcopy(contract["external_white_anchor"]),
        "automatic_chaining": False,
        "retry": False,
        "recovery": False,
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
                raise base.runner.RecheckError("ordinal must be between 1 and 4")
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
            )
    except base.runner.RecheckError as error:
        print(f"same-R20 parity V1 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
