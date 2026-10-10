#!/usr/bin/env python3
"""Fail-closed one-action runner for multi-target history screening V1.

The runner never flashes, resets, controls power, retries, recovers, or
autochains.  It verifies the reviewed local BIN and ELF before any device
request, accepts raw BUSY=1 only, and consumes at most one immutable action
per invocation.  Human observation remains a required gate between separate
invocations; this host does not infer a colour or lightness result.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import ipaddress
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence
import urllib.parse
import urllib.request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_multi_target_history_v1_pack as pack  # noqa: E402


_V3_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_multi_target_history_v1_private_v3_host", _V3_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load BUSY-qualified host mechanics: {_V3_PATH}")
v3 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v3)
v1 = v3.v1
base = v3.base
_V3_VALIDATE_COMPLETE_REPORT = v3._validate_complete_report  # noqa: SLF001

REPORT = pack.build_report()
v3.pack = pack
v3.REPORT = REPORT
base.pack = pack
base._REPORT = REPORT
base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 65.0

base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = "MF1750_EC5_MULTI_TARGET_HISTORY_DEVICE_V1"
base.runner.IDENTITY_REVISION = (
    "runtime-lut-multi-target-history-ab-ba-factory-white-v1"
)
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = (
    "EXPERIMENTAL_L535_MULTI_TARGET_HISTORY_CANDIDATES_NOT_QUALIFIED_COLOURS"
)
base.runner.DEVICE_KIND_PREFIX = "mf1750-ec5-multi-target-history-v1"
base.runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-multi-target-history-v1"
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY

FIRMWARE_SHA256 = "b1f25c890e42f681a39e30a628678041eed4b41ff46f97c13d583ed0c592cb1e"
FIRMWARE_BYTES = 799_552
ELF_SHA256 = "b48be6967d1b6dc9d08ad191e7e149e9cfc77ef6cdaaf3fe5e8e62ab592bb216"
ELF_BYTES = 13_286_676
BUILD_DIR = (
    REPO_ROOT
    / ".pio"
    / "build-runtime-lut-multi-target-history-v1"
    / "ec5_runtime_lut_multi_target_history_v1"
)
base.runner.FIRMWARE_SHA256 = FIRMWARE_SHA256
base.runner.FIRMWARE_BYTES = FIRMWARE_BYTES
base.runner.ENDPOINTS = {
    name: f"/api/ec5/multi-target-history-v1/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = "ARM_ONE_FIXED_MULTI_TARGET_HISTORY_ACTION"
base.runner.EXECUTE_INTENT = "EXECUTE_ARMED_MULTI_TARGET_HISTORY_ACTION_ONCE"
base.runner.ACTIONS = base._actions()
base.runner.DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in base.runner.ACTIONS
)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_runtime_lut_multi_target_history_v1_claims"
)
base.runner.DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RUNTIME_LUT_MULTI_TARGET_HISTORY_20260824_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FACTORY_HEALTH_ROLE = "FACTORY_OTP_WHITE_HEALTH_ANCHOR"
_FACTORY_SEPARATOR_ROLE = "FACTORY_OTP_WHITE_DIRECTION_SEPARATOR"
_CONTAINMENT = REPORT["contract"]["strict_ordinal_progression"]["failure_containment"]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def _private_origin(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
        address = ipaddress.ip_address(parsed.hostname or "")
    except (ValueError, TypeError) as error:
        raise base.runner.RecheckError(
            "base URL must use a literal private/local IPv4 address"
        ) from error
    allowed = any(
        address in network
        for network in (
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
            ipaddress.ip_network("127.0.0.0/8"),
            ipaddress.ip_network("169.254.0.0/16"),
        )
    )
    if (
        parsed.scheme != "http"
        or not isinstance(address, ipaddress.IPv4Address)
        or not allowed
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise base.runner.RecheckError(
            "base URL must be a plain HTTP literal private/local IPv4 origin"
        )
    netloc = str(address) if port is None else f"{address}:{port}"
    return urllib.parse.urlunsplit(("http", netloc, "", "", ""))


def _direct_http_request(
    base_url: str,
    path: str,
    *,
    method: str,
    headers: Mapping[str, str] | None,
    timeout: float,
) -> tuple[int, Mapping[str, Any]]:
    request = urllib.request.Request(
        base_url + path, headers=dict(headers or {}), method=method
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            status = response.getcode()
            payload = response.read(base.runner._MAX_JSON_BYTES + 1)  # noqa: SLF001
    except Exception as error:
        raise base.runner.RecheckError(f"{method} {path} failed: {error}") from error
    if len(payload) > base.runner._MAX_JSON_BYTES:  # noqa: SLF001
        raise base.runner.RecheckError(f"{method} {path} response is too large")
    try:
        result = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise base.runner.RecheckError(
            f"{method} {path} response is not JSON"
        ) from error
    if not isinstance(result, Mapping):
        raise base.runner.RecheckError(
            f"{method} {path} response root is not an object"
        )
    return status, result


def _device_actions() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for host, source in zip(base.runner.ACTIONS, REPORT["actions"], strict=True):
        item = dict(host)
        item["palette_source"] = source["palette_source"]
        item["global_header"] = source["global_header"]
        item["driver_entry"] = (
            "epdDisplayCompiledFactoryOtpWhiteRecovery"
            if source["driver_role"] == "FactoryWhite"
            else "epdDisplayCompiledChromaGrid"
        )
        result.append(item)
    return result


def _firmware_binding() -> dict[str, Any]:
    return {
        "bound": (
            _SHA256_RE.fullmatch(FIRMWARE_SHA256) is not None
            and FIRMWARE_BYTES > 0
            and _SHA256_RE.fullmatch(ELF_SHA256) is not None
            and ELF_BYTES > 0
        ),
        "bin": {
            "path": str(BUILD_DIR / "firmware.bin"),
            "bytes": FIRMWARE_BYTES,
            "sha256": FIRMWARE_SHA256,
        },
        "elf": {
            "path": str(BUILD_DIR / "firmware.elf"),
            "bytes": ELF_BYTES,
            "sha256": ELF_SHA256,
        },
    }


def _verify_local_artifacts() -> None:
    if not _firmware_binding()["bound"]:
        raise base.runner.RecheckError(
            "multi-target firmware binding is malformed; refusing device access"
        )
    for name, byte_count, sha256 in (
        ("firmware.bin", FIRMWARE_BYTES, FIRMWARE_SHA256),
        ("firmware.elf", ELF_BYTES, ELF_SHA256),
    ):
        artifact = BUILD_DIR / name
        if not artifact.is_file():
            raise base.runner.RecheckError(
                f"reviewed multi-target artifact is missing: {artifact}"
            )
        data = artifact.read_bytes()
        if len(data) != byte_count or hashlib.sha256(data).hexdigest() != sha256:
            raise base.runner.RecheckError(
                f"reviewed multi-target artifact identity differs: {artifact}"
            )
    try:
        pack.containment.build_report(verify_artifacts=True)
    except ValueError as error:
        raise base.runner.RecheckError(
            "dedicated multi-target white-containment binding differs; "
            "refusing device access"
        ) from error


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    required_true = (
        "full_screen_global_refresh",
        "multi_target_history_screening",
        "target_repeat_stability_probe",
        "brightness_candidates_only",
        "human_observation_gate_after_every_action",
        "busy_qualified_arm_execute_dispatch",
        "independent_failure_containment_bound",
    )
    required_false = (
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
        "runtime_code7_used_as_white",
    )
    if any(value.get(key) is not True for key in required_true):
        raise base.runner.RecheckError("multi-target capability contract differs")
    if any(value.get(key) is not False for key in required_false):
        raise base.runner.RecheckError(
            "multi-target forbidden capability contract differs"
        )
    if value.get("qualified_colours") != 0:
        raise base.runner.RecheckError("multi-target colour evidence differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="version")  # noqa: SLF001
    if value.get("layout_id") != pack.VARIANT_KEY:
        raise base.runner.RecheckError("multi-target layout identity differs")
    if value.get("action_count") != 9 or value.get("runtime_lut_write") is not True:
        raise base.runner.RecheckError("multi-target action/runtime contract differs")
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
            raise base.runner.RecheckError(f"multi-target safety {key} differs")
    if value.get("nvs_contract") != {
        "namespace": pack.NVS_NAMESPACE,
        "key": pack.NVS_KEY,
        "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
        "phases": {"READY": 0, "ARMED": 1, "CONSUMED": 2, "FAULT": 3},
        "initial_key_present": False,
        "initial_value": 1,
        "initial_next_ordinal": 1,
        "terminal_next_ordinal": 10,
    }:
        raise base.runner.RecheckError("multi-target NVS isolation differs")
    if value.get("baseline_contract") != {
        "ordinal": 1,
        "role": _FACTORY_HEALTH_ROLE,
        "external_anchor_required": False,
        "one_visible_refresh_required": True,
    }:
        raise base.runner.RecheckError("multi-target factory-white baseline differs")
    _validate_capabilities(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    exact = {
        "layout_id": pack.VARIANT_KEY,
        "actions": _device_actions(),
        "action_count": 9,
        "one_driver_call_per_action": True,
        "factory_otp": True,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "automatic_chaining": False,
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "electrical_parameter_write": False,
        "dither": False,
        "spatial_mixing": False,
        "retry": False,
        "recovery": False,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"multi-target manifest {key} differs")
    layout = value.get("history_layout", {})
    expected_layout = {
        "controller_count": 2,
        "controller_width": 512,
        "height": 600,
        "grid_rows": 8,
        "grid_columns_per_controller": 8,
        "cells_per_controller_per_direction": 64,
        "directional_recipes": 128,
        "total_controller_observations": 256,
        "duplicate_recipe_across_controllers": True,
        "controller_color_equivalence_claimed": False,
        "paired_controller_observations_not_waveform_identical": True,
        "controller_payload_binding": ("CS1_ACTIVE535_AND_CS2_COMMENTED535_FIXED"),
        "cs2_position_mirrored": False,
        "grid_x0_local": 20,
        "grid_y0": 40,
        "grid_x1_local_exclusive": 492,
        "grid_y1_exclusive": 560,
        "cell_width": 52,
        "cell_height": 58,
        "gap_x": 8,
        "gap_y": 8,
        "row_axis": "target_code_0_to_7",
        "column_axis": "source_code_0_to_7",
        "horizontal_comparison_group": (
            "eight_adjacent_cells_same_target_different_source"
        ),
        "global_header_sequence": list(pack.GLOBAL_HEADERS),
        "palette_source_sequence": [
            "FACTORY_OTP",
            "L535_RUNTIME",
            "L535_RUNTIME",
            "L535_RUNTIME",
            "FACTORY_OTP",
            "L535_RUNTIME",
            "L535_RUNTIME",
            "L535_RUNTIME",
            "FACTORY_OTP",
        ],
        "factory_otp_white_ordinals": [1, 5, 9],
        "factory_otp_white_fill_byte": 17,
        "runtime_code7_semantics": (
            "unqualified_separator_and_background_transport_code_not_white"
        ),
        "runtime_code7_used_as_white": False,
        "ptlw_command_issued": False,
        "cropped_dtm": False,
        "all_action_dtm_transport": "packed_frame_per_controller",
        "same_boot_prior_complete_required": True,
        "skip_to_factory_white_allowed": False,
        "failure_containment_kind": _CONTAINMENT["kind"],
        "failure_containment_campaign_id": _CONTAINMENT["campaign_id"],
        "failure_containment_contract_id": _CONTAINMENT["contract_id"],
        "failure_containment_firmware_bytes": _CONTAINMENT["firmware_bytes"],
        "failure_containment_firmware_sha256": _CONTAINMENT["firmware_sha256"],
        "failure_containment_elf_bytes": _CONTAINMENT["elf_bytes"],
        "failure_containment_elf_sha256": _CONTAINMENT["elf_sha256"],
        "failure_containment_nvs_namespace": _CONTAINMENT["nvs_namespace"],
        "failure_containment_nvs_key": _CONTAINMENT["nvs_key"],
        "failure_containment_base_route": _CONTAINMENT["base_route"],
        "failure_containment_descriptor_id": _CONTAINMENT["descriptor_id"],
        "failure_containment_action_id": _CONTAINMENT["action_id"],
        "failure_containment_campaign_nvs_dependency": False,
        "failure_containment_automatic_dispatch": False,
        "main_campaign_resume_after_containment": False,
    }
    for key, wanted in expected_layout.items():
        if layout.get(key) != wanted:
            raise base.runner.RecheckError(f"multi-target history layout {key} differs")
    for key in (
        "cs1_r20_prefix_bytes",
        "cs1_r20_prefix_sha256",
        "cs2_r20_prefix_bytes",
        "cs2_r20_prefix_sha256",
        "r21_bytes",
        "r21_sha256",
    ):
        if layout.get(key) != REPORT["contract"]["profiles"]["active"][key]:
            raise base.runner.RecheckError(f"multi-target LUT {key} differs")
    _validate_capabilities(value)


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_busy: int
) -> str:
    if not 1 <= ordinal <= 9 or expected_busy != 1 or value.get("busy") != 1:
        raise base.runner.RecheckError(
            "multi-target every ordinal requires raw ready BUSY=1"
        )
    nonce = v1._BASE_VALIDATE_READY_STATUS(  # noqa: SLF001
        value, ordinal, expected_busy=1
    )
    for key in (
        "arm_request_count",
        "execute_request_count",
        "total_driver_call_count",
    ):
        if value.get(key) != ordinal - 1:
            raise base.runner.RecheckError(f"multi-target ready status {key} differs")
    return nonce


def _validate_prior_terminal_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    if ordinal <= 1:
        raise base.runner.RecheckError("multi-target prior ordinal differs")
    v3._validate_complete_report(value, ordinal - 1, boot_nonce)  # noqa: SLF001
    if ordinal == 2 and value.get("role") != _FACTORY_HEALTH_ROLE:
        raise base.runner.RecheckError(
            "ordinal 2 requires prior factory-white health COMPLETE"
        )
    if ordinal == 6 and value.get("role") != _FACTORY_SEPARATOR_ROLE:
        raise base.runner.RecheckError(
            "ordinal 6 requires prior factory-white separator COMPLETE"
        )


def _validate_complete_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    _V3_VALIDATE_COMPLETE_REPORT(value, ordinal, boot_nonce)
    source = REPORT["actions"][ordinal - 1]
    exact = {
        "palette_source": source["palette_source"],
        "global_header": source["global_header"],
        "driver_entry": (
            "epdDisplayCompiledFactoryOtpWhiteRecovery"
            if source["driver_role"] == "FactoryWhite"
            else "epdDisplayCompiledChromaGrid"
        ),
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(
                f"multi-target COMPLETE transport {key} differs"
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
) -> dict[str, Any]:
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
    value["variant"] = deepcopy(REPORT["contract"])
    value["firmware_binding"] = _firmware_binding()
    value["artifact_preflight_required_before_device_access"] = True
    value["preflight_busy_contract"] = {
        "ordinals_1_to_9": "RAW_READY_BUSY_1_ONLY",
        "busy_zero_accepted": False,
        "firmware_gates": ["ARM", "EXECUTE", "DISPATCH"],
    }
    value["fixed_transport"] = {
        "spi_hz": 1_000_000,
        "factory_otp_white_ordinals": [1, 5, 9],
        "factory_otp_white_frame_fill_byte": "0x11",
        "runtime_lut_ordinals": [2, 3, 4, 6, 7, 8],
        "global_header_sequence": list(pack.GLOBAL_HEADERS),
        "packed_full_frame_per_controller": True,
        "ptlw_command_issued": False,
        "partial_refresh": False,
        "unknown_commands": False,
        "spatial_dither": False,
        "runtime_code7_used_as_white": False,
        "runtime_code7_semantics": (
            "unqualified_separator_and_background_transport_code_not_white"
        ),
        "directional_recipes": 128,
        "controller_observations": 256,
        "qualified_colours": 0,
        "blocking_refresh_first_poll_floor_seconds": 65.0,
    }
    value["ordinal_progression"] = {
        "strict_same_boot_prior_complete_required": True,
        "terminal_next_ordinal": 10,
        "skip_to_factory_white": False,
        "one_action_per_invocation": True,
        "human_observation_gate_between_invocations_required": True,
        "human_observation_receipt_machine_enforced": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
        "visual_or_terminal_failure_containment": deepcopy(_CONTAINMENT),
    }
    value["ordinal_progression"]["visual_or_terminal_failure_containment"][
        "artifact_binding_status"
    ] = pack.containment.artifact_binding_status()
    value["evidence_boundary"] = {
        "transport_codes_not_qualified_colours": True,
        "brightness_candidates_not_levels": True,
        "controller_repeats_not_additional_unique_colours": True,
        "controller_colour_equivalence_not_claimed": True,
        "separator_code7_not_called_white": True,
        "local_hold_not_tested_or_claimed": True,
        "active_commented_difference_is_global_header_only": True,
        "reported_dispatch_is_reviewed_software_not_bus_measurement": True,
        "paired_controllers_are_analogous_not_waveform_identical": True,
    }
    return value


# Rebind every dynamic validation point in the isolated host stack.
v3._validate_capabilities = _validate_capabilities
v3._validate_version = _validate_version
v3._validate_manifest = _validate_manifest
v3._validate_ready_status = _validate_ready_status
v3._validate_prior_terminal_report = _validate_prior_terminal_report
v3._validate_complete_report = _validate_complete_report
v3._preflight = _preflight
base._validate_capabilities = _validate_capabilities
base._validate_version = _validate_version
base._validate_manifest = _validate_manifest
base.runner._validate_version = _validate_version
base.runner._validate_manifest = _validate_manifest
base.runner._validate_ready_status = _validate_ready_status
base.runner._preflight = _preflight
base.runner._origin = _private_origin
base.runner._http_request = _direct_http_request
base.runner.run_once = run_once
base.runner.describe = describe
v1._validate_version = _validate_version
v1._validate_manifest = _validate_manifest
v1._preflight = _preflight


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    run = sub.add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--ordinal", type=int, choices=range(1, 10), required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument(
        "--confirm-human-observation-gate", action="store_true", required=True
    )
    run.add_argument("--claims", type=Path, default=base.runner.DEFAULT_CLAIMS)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--poll-seconds", type=float, default=65.0)
    run.add_argument("--poll-count", type=int, default=60)
    salvage = sub.add_parser("salvage-fault")
    salvage.add_argument("--base-url", required=True)
    salvage.add_argument("--ordinal", type=int, choices=range(1, 10), required=True)
    salvage.add_argument("--claims", type=Path, default=base.runner.DEFAULT_CLAIMS)
    salvage.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "describe":
            value = describe()
        elif args.command == "salvage-fault":
            value = salvage_fault_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output,
            )
        else:
            value = run_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except base.runner.RecheckError as error:
        print(f"multi-target history V1 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
