#!/usr/bin/env python3
"""Offline Stage-B read-only diagnostic facade blueprint and fake harness.

This module deliberately contains no HTTP, serial, subprocess, hardware, or
live-execution entry point.  It deep-binds the V10 diagnostic-recovery plan and
the partial Stage-A boot-control receipt, specifies the future one-origin
bodyless-GET state machine, and exercises that state machine only through an
exact in-memory scripted fake.

The Stage-A receipt is *not* promoted to a completed Stage-A receipt.  Under a
future, explicit superseding authority contract, the first exact ``/version``
response may establish only V10 protocol-response conformance for the one
operator-selected candidate origin and unlock the remaining read-only budget.
It cannot prove responder/device identity, a trusted IP binding, fresh boot, or
the active application.  This blueprint does not create that authority, an
onsite receipt, a user authorization, or a live executor.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, BinaryIO, Final, Mapping, Sequence

from tools import mf1750_ec5_h3_c_first_diagnostic_recovery_contract as recovery
from tools import mf1750_ec5_h3_matched_control_contract as contract
from tools import mf1750_ec5_h3_v10_stage_a_boot_receipt as stage_a
from tools.mf1750_ec5_h3_matched_control_physical_once import (
    _expect_manifest as _frozen_expect_manifest,
    _expect_preflight_report as _frozen_expect_preflight_report,
    _expect_status as _frozen_expect_status,
    _expect_version as _frozen_expect_version,
    load_release as _load_frozen_v10_release,
)


SCHEMA_VERSION: Final = 2
KIND: Final = "mf1750-ec5-h3-c-first-stage-b-read-only-facade-blueprint-v2"
CLASSIFICATION: Final = (
    "OFFLINE_FAKE_ONLY_EXACT_SURFACE_BLUEPRINT_NOT_LIVE_AUTHORIZATION"
)
FAKE_RESULT_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-read-only-facade-fake-result-v2"
)
FAKE_RESULT_CLASSIFICATION: Final = "SYNTHETIC_FAKE_ONLY_NOT_DEVICE_EVIDENCE"
MAX_JSON_BYTES: Final = 4_000_000
EXPECTED_PLAN_ID: Final = stage_a.EXPECTED_PLAN_ID
EXPECTED_PLAN_FILE_SHA256: Final = stage_a.EXPECTED_PLAN_FILE_SHA256
EXPECTED_PLAN_CANONICAL_SHA256: Final = stage_a.EXPECTED_PLAN_CANONICAL_SHA256
EXPECTED_STAGE_A_INTENT_SHA256: Final = stage_a.EXPECTED_STAGE_A_INTENT_SHA256
EXPECTED_RELEASE_ID: Final = recovery.EXPECTED_RELEASE_ID
EXPECTED_FIRMWARE_SHA256: Final = recovery.EXPECTED_CONTROL_BINARY_SHA256
EXPECTED_VALIDATOR_MODULE_SHA256: Final = (
    "a46e4ad298fe415c35ebeaaa640e969773ca498ca5ca4345255bbe7163beba38"
)
EXPECTED_CONTROL_MAIN_SHA256: Final = (
    "90608c8a71ee773a62029c15e98bf6542c9f01ba805407482138979efbf009ca"
)
EXPECTED_ONCE_MAIN_SHA256: Final = (
    "c91b26d1e1c1f93dae78425e55abe4b725f0244e9d7830fc28e2fc23fc95c470"
)
EXPECTED_CONTROL_DRIVER_SHA256: Final = (
    "5747aecc65501baaba2cab3ba36d700fcc4192dc7c802f91ce879f1f58378ae7"
)
EXPECTED_REFERENCE_PROFILE_SHA256: Final = (
    "8009f2c5523bd4c592474cc15e6b0b4a8b0a74053a09e69d4926d9f5abffb626"
)
SUPERSEDED_V1_BLUEPRINT_FILE_SHA256: Final = (
    "2ea8fa17fdf8639ba9736c1f88471188aa989d60a95e4db96fe9194ce960ceb9"
)
SUPERSEDED_V1_BLUEPRINT_ID: Final = (
    "1dbdf4af9ba52aeff9786aebcdfdb888c61b4ebae21b69a509664f3aefe1bc77"
)
SUPERSEDED_V1_BLUEPRINT_CANONICAL_SHA256: Final = (
    "425790cb90c6ce84e72573c8469f8d21f6c1b37c99e1ebdba7dd7e0127258bba"
)
ENDPOINT_NAMES: Final = ("version", "manifest", "status", "report")
FROZEN_VALIDATOR_NAMES: Final = (
    "_expect_version",
    "_expect_manifest",
    "_expect_status",
    "_expect_preflight_report",
)
BOOT_NONCE_PATTERN: Final = re.compile(r"^[0-9a-f]{16}$")
EXPECTED_DEVICE_CLASSIFICATION: Final = (
    "EMPIRICAL_H3_MATCHED_NEGATIVE_CONTROL_NO_R20_R21_NOT_AUTHORIZED"
)
EXPECTED_IDENTITY_REVISION: Final = "h3-matched-no-r20-r21-c-first-v2"
EXPECTED_COMMAND_AUDIT_MARKER: Final = (
    "MF1750_EC5_H3_MATCHED_CONTROL_COMMAND_AUDIT_V2|"
    "R20_COMMAND_WRITES=0|R21_COMMAND_WRITES=0|R20_BYTES=0|R21_BYTES=0|"
    "DESIGN=E9_ONLY_DELETE_ONLY_NOT_TIME_MATCHED"
)
EXPECTED_PROFILE_SOURCE_SHA256: Final = (
    "0dd568cca1d18cdd475a9ef5c7b7b2b56f11dc5abeeeb5d478b28f7bcb65e821"
)
EXPECTED_DECODED_HEADER_SHA256: Final = (
    "2fc6ab4de405835d9a5ff93a19adb03e277d0dece9df87a88c467a07bcb801af"
)
EXPECTED_POWER_PAYLOAD_SHA256: Final = (
    "44a59eb14f6766b6f7de20019ee9739c7ab262c02e6b5e4a48f22e87c289b917"
)
EXPECTED_PLL_PAYLOAD_SHA256: Final = (
    "dbc1b4c900ffe48d575b5da5c638040125f65db0fe3e24494b76ea986457d986"
)
EXPECTED_RISK_CLAIMS: Final = (
    "PSR_5F69_TO_5FE9_DERIVATION_AND_INSERTION",
    "WF20_25_HEADER_PWR_PLL_BINDING_AND_ORDER",
    "E9_01_MEANING_AND_BUSY_SEMANTICS",
    "CROSS_GENERATION_SEQUENCE_ON_SPD1657_E2802",
    "CS2_ACCEPTANCE_WITHOUT_READBACK_AND_SINGLE_BUSY",
    "PANEL_FPL_FILM_LOT_TEMPERATURE_AND_VCOM_MATCH",
    "NO_R20_R21_RESULT_IDENTIFIES_HIDDEN_FALLBACK_STATE",
    "POST_POF_TO_FACTORY_OTP_RECOVERY_CONTRACT",
)


class StageBFacadeContractError(ValueError):
    """A facade binding, prerequisite, reservation, or fake step differs."""


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    root = deepcopy(dict(unsigned))
    root["integrity"] = {
        "algorithm": "sha256",
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
        "canonical_sha256": contract.sha256(root),
    }
    return root


def _validate_seal(root: Mapping[str, Any], *, label: str) -> str:
    unsigned = {key: value for key, value in root.items() if key != "integrity"}
    expected = _seal(unsigned)["integrity"]
    if root.get("integrity") != expected:
        raise StageBFacadeContractError(f"{label} canonical integrity differs")
    return str(expected["canonical_sha256"])


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_regular(path: Path, *, label: str) -> tuple[Path, bytes]:
    target = Path(os.path.abspath(os.fspath(path)))
    try:
        before = target.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise StageBFacadeContractError(
                f"{label} must be a non-symlink regular file"
            )
        if before.st_size <= 0 or before.st_size > MAX_JSON_BYTES:
            raise StageBFacadeContractError(f"{label} size is invalid")
        payload = target.read_bytes()
        after = target.lstat()
    except OSError as error:
        raise StageBFacadeContractError(f"could not read {label}: {error}") from error
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(payload) != after.st_size:
        raise StageBFacadeContractError(f"{label} changed while being read")
    return target, payload


def _decode_json(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise StageBFacadeContractError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(root, Mapping):
        raise StageBFacadeContractError(f"{label} root is not an object")
    return root


def _read_json(path: Path, *, label: str) -> tuple[Path, bytes, Mapping[str, Any]]:
    resolved, payload = _read_regular(path, label=label)
    return resolved, payload, _decode_json(payload, label=label)


def _assert_directory_chain(path: Path, *, create: bool, label: str) -> Path:
    directory = Path(os.path.abspath(os.fspath(path)))

    def inspect() -> None:
        for candidate in reversed((directory, *directory.parents)):
            try:
                info = candidate.lstat()
            except FileNotFoundError:
                continue
            except OSError as error:
                raise StageBFacadeContractError(
                    f"could not inspect {label} directory: {error}"
                ) from error
            if stat.S_ISLNK(info.st_mode):
                raise StageBFacadeContractError(
                    f"{label} directory chain contains a symlink"
                )
            if not stat.S_ISDIR(info.st_mode):
                raise StageBFacadeContractError(
                    f"{label} parent chain is not a directory"
                )

    inspect()
    if create:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise StageBFacadeContractError(
                f"could not create {label} directory: {error}"
            ) from error
        inspect()
    return directory


def _file_binding(path: Path, *, label: str) -> dict[str, Any]:
    resolved, payload = _read_regular(path, label=label)
    return {
        "path": str(resolved),
        "bytes": len(payload),
        "sha256": contract.sha256(payload),
    }


def _ordered_requests(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    budget = plan["read_only_diagnostic_budget"]
    requests = budget["ordered_requests"]
    if not isinstance(requests, list) or len(requests) != len(ENDPOINT_NAMES):
        raise StageBFacadeContractError("plan ordered request surface differs")
    base_route = str(plan["v10_release"]["control_artifact"]["base_route"])
    expected = [
        {"ordinal": index, "method": "GET", "path": f"{base_route}/{name}"}
        for index, name in enumerate(ENDPOINT_NAMES, start=1)
    ]
    if requests != expected:
        raise StageBFacadeContractError("plan ordered request surface differs")
    return expected


def _require_exact_value(actual: Any, expected: Any, *, label: str) -> None:
    """Compare a decoded JSON value with exact recursive type/key semantics."""

    if type(actual) is not type(expected):
        raise StageBFacadeContractError(f"{label} JSON type differs")
    if type(expected) is dict:
        actual_keys = set(actual)
        expected_keys = set(expected)
        if actual_keys != expected_keys:
            missing = sorted(expected_keys - actual_keys)
            extra = sorted(actual_keys - expected_keys)
            raise StageBFacadeContractError(
                f"{label} exact key set differs; missing={missing}, extra={extra}"
            )
        for key in expected:
            _require_exact_value(actual[key], expected[key], label=f"{label}.{key}")
        return
    if type(expected) is list:
        if len(actual) != len(expected):
            raise StageBFacadeContractError(f"{label} list length differs")
        for index, (observed, wanted) in enumerate(zip(actual, expected, strict=True)):
            _require_exact_value(observed, wanted, label=f"{label}[{index}]")
        return
    if actual != expected:
        raise StageBFacadeContractError(f"{label} value differs")


def _expected_identity(context: Any, ordinal: int) -> dict[str, Any]:
    action = context.action(ordinal)
    binding = context.binding(ordinal)
    return {
        "build_tag": binding["build_tag"],
        "test_id": binding["test_id"],
        "campaign_id": binding["campaign_id"],
        "profile_id": context.profile_id,
        "environment": binding["environment"],
        "device_api_version": contract.DEVICE_API_VERSION,
        "identity_revision": EXPECTED_IDENTITY_REVISION,
        "running_app_elf_sha256": binding["firmware_elf_sha256"],
        "contract_id": context.root["contract_id"],
        "transaction_descriptor_sha256": binding["transaction_descriptor_sha256"],
        "transaction_descriptor_marker": contract.compiled_descriptor_marker(
            context.profile_id, action["role"]
        ),
        "command_audit_marker": EXPECTED_COMMAND_AUDIT_MARKER,
    }


def _expected_profile_surface(context: Any) -> dict[str, Any]:
    electrical = contract.profile_row()["requested_electrical_metadata"]
    return {
        "profile_id": context.profile_id,
        "compiled_profile_count": 1,
        "auto_selected": False,
        "source_artifact_sha256": EXPECTED_PROFILE_SOURCE_SHA256,
        "decoded_header_sha256": EXPECTED_DECODED_HEADER_SHA256,
        "pwr_payload_sha256": EXPECTED_POWER_PAYLOAD_SHA256,
        "pll_payload_sha256": EXPECTED_PLL_PAYLOAD_SHA256,
        "apparent_temperature_min_c": 20,
        "apparent_temperature_max_c": 25,
        "requested_gate_positive_mv": electrical["gate_positive_mv"],
        "requested_gate_negative_mv": electrical["gate_negative_mv"],
        "requested_full_source_positive_mv": electrical["full_source_positive_mv"],
        "requested_full_source_negative_mv": electrical["full_source_negative_mv"],
        "requested_vsh_lv_mv": electrical["intermediate_source_mv"]["vsh_lv"],
        "requested_vsl_lv_mv": electrical["intermediate_source_mv"]["vsl_lv"],
        "requested_vsh_lv2_mv": electrical["intermediate_source_mv"]["vsh_lv2"],
        "requested_vsl_lv2_mv": electrical["intermediate_source_mv"]["vsl_lv2"],
        "requested_frame_rate_hz": electrical["frame_rate_hz"],
        "electrical_values_source": "matched_wf20_25_constants",
        "panel_or_fpl_limits_proven": False,
        "r20_command_writes": 0,
        "r21_command_writes": 0,
        "r20_payload_bytes": 0,
        "r21_payload_bytes": 0,
        "empirical_cross_version": True,
        "matched_negative_control": True,
        "vendor_proven_sequence": False,
        "live_authorized": False,
    }


def _expected_version_surface(context: Any, ordinal: int = 1) -> dict[str, Any]:
    binding = context.binding(ordinal)
    return {
        "schema_version": 1,
        "kind": f"{binding['kind_prefix']}-version",
        **_expected_identity(context, ordinal),
        "classification": EXPECTED_DEVICE_CLASSIFICATION,
        "profile": _expected_profile_surface(context),
        "action_count": 1,
        "startup_refresh": False,
        "raw_ingress": False,
        "retry": False,
        "automatic_chaining": False,
        "automatic_recovery": False,
        "profile_switch": False,
        "live_authorized": False,
    }


def _expected_manifest_surface(context: Any, ordinal: int = 1) -> dict[str, Any]:
    action = context.action(ordinal)
    binding = context.binding(ordinal)
    risks = [
        {"id": f"C{index}", "status": "unproven", "claim": claim}
        for index, claim in enumerate(EXPECTED_RISK_CLAIMS, start=1)
    ]
    return {
        "schema_version": 1,
        "kind": f"{binding['kind_prefix']}-manifest",
        **_expected_identity(context, ordinal),
        "classification": EXPECTED_DEVICE_CLASSIFICATION,
        "profile": _expected_profile_surface(context),
        "action_count": 1,
        "one_driver_call_per_action": True,
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "raw_lut_ingress": False,
        "electrical_parameter_ingress": False,
        "timing_parameter_ingress": False,
        "retry": False,
        "automatic_chaining": False,
        "automatic_recovery": False,
        "profile_switch": False,
        "vcom_write": False,
        "vcom_sweep": False,
        "requires_new_exact_authorization": True,
        "j2_state_is_operator_assertion_not_firmware_detection": True,
        "actions": [
            {
                "ordinal": ordinal,
                "role": action["role"],
                "descriptor_id": action["transaction_descriptor_sha256"],
                "action_id": action["hardware_action_id"],
                "frame_sha256": action["payload_identity"]["frame_sha256"],
                "cs1_dtm_sha256": action["payload_identity"]["cs1_dtm_sha256"],
                "cs2_dtm_sha256": action["payload_identity"]["cs2_dtm_sha256"],
            }
        ],
        "unproven_risks": risks,
        "r20_command_writes": 0,
        "r21_command_writes": 0,
        "r20_payload_bytes": 0,
        "r21_payload_bytes": 0,
        "control_design": contract.CONTROL_DESIGN,
        "strict_payload_only_control": False,
        "time_matched_control": False,
        "dummy_clocks_inserted": False,
        "empty_r20_or_r21_commands_inserted": False,
        "per_controller_removed_spi_bytes_and_edges": 1505,
        "per_controller_removed_cooperative_yields": 5,
        "e9_and_busy_gate_preserved": True,
        "matched_sequence": {
            "factory_dual_init_first": True,
            "factory_psr": "5F69",
            "factory_e0_per_controller": True,
            "global_exact_order": [
                "PSR_5FE9",
                "PWR_FROM_WF20_25_HEADER",
                "IDLE_GATE_AFTER_PWR",
                "PLL_FROM_WF20_25_HEADER",
                "TRES_512X600",
            ],
            "per_controller_exact_order": [
                "CS1_E9_01",
                "IDLE_GATE_AFTER_CS1_E9",
                "CS2_E9_01",
                "IDLE_GATE_AFTER_CS2_E9",
            ],
            "r20_command_writes": 0,
            "r21_command_writes": 0,
            "r20_bytes": 0,
            "r21_bytes": 0,
            "dtm_frame_identical_to_h3_atlas": True,
            "dtm_controller_order": ["CS1", "CS2"],
            "synchronous_refresh": True,
            "waveform_readback": False,
            "single_busy_observes_master_only": True,
        },
        "no_difference_interpretation": "NO_DETECTABLE_INCREMENTAL_EFFECT",
        "payload_only_attribution_proven": False,
        "attribution_scope": (
            "VISIBLE_DIFFERENCE_VS_H3_CAN_SUPPORT_BUT_NOT_ALONE_PROVE_"
            "R20_R21_ACCEPTANCE"
        ),
        "separate_otp_white_recovery_required": True,
        "nvs_contract": {
            "namespace": binding["nvs_namespace"],
            "key": "used_v2",
            "encoding": "uint16_high_byte_phase_low_byte_ordinal",
            "initial_cursor": ordinal,
            "terminal_cursor": ordinal + 1,
            "clear_route": False,
            "persistent_across_reboot": True,
        },
    }


def _expected_status_surface(
    context: Any, *, boot_nonce: str, busy: int, ordinal: int = 1
) -> dict[str, Any]:
    binding = context.binding(ordinal)
    return {
        "schema_version": 1,
        "kind": f"{binding['kind_prefix']}-status",
        **_expected_identity(context, ordinal),
        "boot_nonce": boot_nonce,
        "state": "ready",
        "phase": 0,
        "phase_name": "READY",
        "cursor_raw": ordinal,
        "next_ordinal": ordinal,
        "campaign_complete": False,
        "fixture_self_check_passed": True,
        "cursor_valid": True,
        "persistent_key_present": False,
        "execute_pending": False,
        "arm_request_count": 0,
        "execute_request_count": 0,
        "total_driver_call_count": 0,
        "gpio_initialized": True,
        "busy": busy,
        "rst": 0,
        "cs": 0,
        "cs2": 0,
        "sck": 0,
        "dc": 0,
        "mosi": 0,
    }


def _expected_report_surface(context: Any, ordinal: int = 1) -> dict[str, Any]:
    binding = context.binding(ordinal)
    return {
        "schema_version": 1,
        "kind": f"{binding['kind_prefix']}-report",
        "valid": False,
        **_expected_identity(context, ordinal),
        "terminal_state": "NOT_EXECUTED",
        "result": False,
        "error": "no_execute_report",
        "driver_called": False,
        "driver_call_count_for_action": 0,
        "no_retry": True,
        "r20_command_writes": 0,
        "r21_command_writes": 0,
        "r20_payload_bytes": 0,
        "r21_payload_bytes": 0,
        "matched_negative_control": True,
        "control_design": contract.CONTROL_DESIGN,
        "strict_payload_only_control": False,
        "time_matched_control": False,
        "dummy_clocks_inserted": False,
        "empty_r20_or_r21_commands_inserted": False,
        "per_controller_removed_spi_bytes_and_edges": 1505,
        "per_controller_removed_cooperative_yields": 5,
        "no_difference_interpretation": "NO_DETECTABLE_INCREMENTAL_EFFECT",
    }


def _validate_response_surface(
    name: str, value: Mapping[str, Any], context: Any, ordinal: int = 1
) -> str | None:
    """Validate the source-shaped exact surface plus compatible legacy subset."""

    if type(value) is not dict:
        raise StageBFacadeContractError(f"{name} response must be a plain JSON object")
    if name == "version":
        # The legacy subset validator incorrectly requires five manifest-root
        # sequence fields inside version.profile.  Applying it to the real V10
        # source-shaped version is therefore forbidden.
        _require_exact_value(
            value, _expected_version_surface(context, ordinal), label="version"
        )
        return None
    if name == "manifest":
        _frozen_expect_manifest(value, context, ordinal)
        _require_exact_value(
            value, _expected_manifest_surface(context, ordinal), label="manifest"
        )
        return None
    if name == "status":
        boot_nonce = value.get("boot_nonce")
        busy = value.get("busy")
        if (
            type(boot_nonce) is not str
            or BOOT_NONCE_PATTERN.fullmatch(boot_nonce) is None
        ):
            raise StageBFacadeContractError("status boot_nonce is invalid")
        if type(busy) is not int or busy not in (0, 1):
            raise StageBFacadeContractError("status busy is invalid")
        subset_nonce = _frozen_expect_status(value, context, ordinal)
        _require_exact_value(
            value,
            _expected_status_surface(
                context, boot_nonce=boot_nonce, busy=busy, ordinal=ordinal
            ),
            label="status",
        )
        if subset_nonce != boot_nonce:
            raise StageBFacadeContractError("status subset nonce differs")
        return boot_nonce
    if name == "report":
        _frozen_expect_preflight_report(value, context, ordinal)
        _require_exact_value(
            value, _expected_report_surface(context, ordinal), label="report"
        )
        return None
    raise StageBFacadeContractError(f"unknown response surface {name!r}")


def validate_v10_response_surface(
    name: str, value: Mapping[str, Any], context: Any, ordinal: int = 1
) -> str | None:
    """Reusable source-pinned V10 C diagnostic response validator.

    ``version`` intentionally does not invoke the incompatible legacy subset
    validator.  The remaining three responses use the compatible frozen
    subset first and then the exact source-shaped surface.
    """

    return _validate_response_surface(name, value, context, ordinal)


def decode_and_validate_v10_response_bytes(
    name: str, payload: bytes, context: Any, ordinal: int = 1
) -> tuple[Mapping[str, Any], str | None]:
    """Strictly decode and source-validate one raw V10 response body.

    This is the single reusable boundary for the fake state machine and any
    future separately authorized live facade.  It intentionally accepts raw
    bytes only, applies the response-size budget before decoding, rejects
    non-strict JSON, and performs the endpoint validator before returning.
    """

    if type(payload) is not bytes:
        raise StageBFacadeContractError(f"{name} response body must be raw bytes")
    if len(payload) <= 0 or len(payload) > MAX_JSON_BYTES:
        raise StageBFacadeContractError(f"{name} response body size is invalid")
    value = _decode_json(payload, label=f"{name} response body")
    observed_nonce = _validate_response_surface(name, value, context, ordinal)
    return value, observed_nonce


def expected_v10_response_fixture(
    name: str,
    context: Any,
    *,
    ordinal: int = 1,
    boot_nonce: str = "0123456789abcdef",
    busy: int = 1,
) -> dict[str, Any]:
    """Return a source-shaped in-memory fixture for offline tests only."""

    if name == "version":
        return _expected_version_surface(context, ordinal)
    if name == "manifest":
        return _expected_manifest_surface(context, ordinal)
    if name == "status":
        return _expected_status_surface(
            context, boot_nonce=boot_nonce, busy=busy, ordinal=ordinal
        )
    if name == "report":
        return _expected_report_surface(context, ordinal)
    raise StageBFacadeContractError(f"unknown response fixture {name!r}")


def materialize_blueprint(
    *,
    plan_file: Path,
    stage_a_receipt_file: Path,
    blueprint_file: Path,
    _require_live_output_absent: bool = True,
) -> dict[str, Any]:
    """Deep-bind the current plan and partial Stage-A receipt offline."""

    plan_path, plan_payload, plan = _read_json(plan_file, label="recovery plan")
    if contract.sha256(plan_payload) != EXPECTED_PLAN_FILE_SHA256:
        raise StageBFacadeContractError("recovery plan whole-file SHA-256 differs")
    try:
        plan_summary = recovery.validate_plan(
            plan, require_new_output_absent=_require_live_output_absent
        )
    except recovery.DiagnosticRecoveryContractError as error:
        raise StageBFacadeContractError(
            f"recovery plan validation failed: {error}"
        ) from error
    exact_plan = {
        "plan_id": EXPECTED_PLAN_ID,
        "canonical_sha256": EXPECTED_PLAN_CANONICAL_SHA256,
        "stage_a_new_boot_intent_sha256": EXPECTED_STAGE_A_INTENT_SHA256,
        "release_id": EXPECTED_RELEASE_ID,
        "firmware_binary_sha256": EXPECTED_FIRMWARE_SHA256,
    }
    for key, expected in exact_plan.items():
        if plan_summary.get(key) != expected:
            raise StageBFacadeContractError(f"recovery plan {key} differs")

    receipt_path, receipt_payload, receipt = _read_json(
        stage_a_receipt_file, label="Stage-A partial receipt"
    )
    try:
        receipt_summary = stage_a.validate_receipt(receipt)
    except stage_a.StageABootReceiptError as error:
        raise StageBFacadeContractError(
            f"Stage-A partial receipt validation failed: {error}"
        ) from error
    if (
        receipt_summary.get("classification") != stage_a.CLASSIFICATION
        or receipt_summary.get("stage_a_intent_satisfied") is not False
        or receipt_summary.get("active_v10_proven") is not False
        or receipt_summary.get("ip_proven") is not False
        or receipt_summary.get("stage_b_authorization_derivable") is not False
    ):
        raise StageBFacadeContractError(
            "Stage-A receipt must remain partial and non-authorizing"
        )
    receipt_plan = receipt.get("plan_binding")
    if not isinstance(receipt_plan, Mapping) or (
        receipt_plan.get("path") != str(plan_path)
        or receipt_plan.get("sha256") != contract.sha256(plan_payload)
        or receipt_plan.get("plan_id") != plan_summary["plan_id"]
        or receipt_plan.get("canonical_sha256") != plan_summary["canonical_sha256"]
        or receipt_plan.get("stage_a_intent_canonical_sha256")
        != plan_summary["stage_a_new_boot_intent_sha256"]
    ):
        raise StageBFacadeContractError(
            "Stage-A receipt does not bind this exact recovery plan"
        )

    validator_binding = _file_binding(
        Path(_frozen_expect_version.__code__.co_filename),
        label="frozen V10 validator module",
    )
    if validator_binding["sha256"] != EXPECTED_VALIDATOR_MODULE_SHA256:
        raise StageBFacadeContractError("frozen V10 validator module SHA-256 differs")
    exact_surface_sources = {
        "exact_surface_validator_module": _file_binding(
            Path(__file__), label="exact response-surface validator module"
        ),
        "v10_control_main": _file_binding(
            contract.REPO_ROOT / "src" / "ec5_h3_matched_control_main.cpp",
            label="V10 control main source",
        ),
        "v10_shared_http_envelope": _file_binding(
            contract.REPO_ROOT / "src" / "ec5_h3_matched_control_once_main.inc",
            label="V10 shared HTTP envelope source",
        ),
        "v10_control_driver_constants": _file_binding(
            contract.REPO_ROOT / "src" / "ec5_h3_matched_control_driver.inc",
            label="V10 control driver constants source",
        ),
    }
    reference_profile = {
        **_file_binding(
            contract.REPO_ROOT
            / "src"
            / "generated"
            / "spd1657_wf20_25_empirical_h3.inc",
            label="WF20_25 generated reference profile",
        ),
        "role": "REFERENCE_NOT_COMPILED_INTO_CONTROL_NOT_RESPONSE_SOURCE_PROOF",
    }
    expected_compiled_source_hashes = {
        "v10_control_main": EXPECTED_CONTROL_MAIN_SHA256,
        "v10_shared_http_envelope": EXPECTED_ONCE_MAIN_SHA256,
        "v10_control_driver_constants": EXPECTED_CONTROL_DRIVER_SHA256,
    }
    for source_name, expected_sha256 in expected_compiled_source_hashes.items():
        if exact_surface_sources[source_name]["sha256"] != expected_sha256:
            raise StageBFacadeContractError(
                f"V10 compiled response source SHA-256 differs for {source_name}"
            )
    if reference_profile["sha256"] != EXPECTED_REFERENCE_PROFILE_SHA256:
        raise StageBFacadeContractError(
            "WF20_25 reference-only generated profile SHA-256 differs"
        )
    release_context = _load_frozen_v10_release(Path(plan["v10_release"]["path"]))
    release_source = release_context.root["compiled_images"][
        "matched_no_r20_r21_control"
    ]["firmware"]["transaction_source"]
    bound_main = exact_surface_sources["v10_control_main"]
    transitive = release_context.root["compiled_treatment_control_trace_audit"][
        "transitive_build_manifest"
    ]["control"]["repo_local_dependencies"]

    def require_transitive(path_id: str, observed: Mapping[str, Any]) -> None:
        matches = [item for item in transitive if item.get("path_id") == path_id]
        if len(matches) != 1 or (
            matches[0].get("bytes") != observed["bytes"]
            or matches[0].get("sha256") != observed["sha256"]
        ):
            raise StageBFacadeContractError(
                f"V10 transitive source binding differs for {path_id}"
            )

    require_transitive("repo/src/ec5_h3_matched_control_main.cpp", bound_main)
    require_transitive(
        "repo/src/ec5_h3_matched_control_once_main.inc",
        exact_surface_sources["v10_shared_http_envelope"],
    )
    require_transitive(
        "repo/src/ec5_h3_matched_control_driver.inc",
        exact_surface_sources["v10_control_driver_constants"],
    )
    if (
        plan["v10_release"]["control_artifact"]["binary"]["sha256"]
        != EXPECTED_FIRMWARE_SHA256
        or release_source["path"] != bound_main["path"]
        or release_source["bytes"] != bound_main["bytes"]
        or release_source["sha256"] != bound_main["sha256"]
    ):
        raise StageBFacadeContractError("V10 release control binary differs")

    ordered = _ordered_requests(plan)
    base_url = str(plan["network_locator"]["candidate_base_url"])
    absolute = [
        {**item, "absolute_url": f"{base_url}{item['path']}"} for item in ordered
    ]
    live_output = Path(str(plan["new_attempt"]["new_diagnostic_output"]))
    output_path = Path(os.path.abspath(os.fspath(blueprint_file)))
    if output_path == live_output:
        raise StageBFacadeContractError(
            "blueprint output must differ from the planned diagnostic output"
        )
    superseded_path, superseded_payload, superseded_root = _read_json(
        contract.REPO_ROOT
        / ".test-output"
        / "offline"
        / "MF1750_EC5_H3_C_FIRST_STAGE_B_FACADE_BLUEPRINT_20260815_V1"
        / "WF20_25-blueprint.json",
        label="superseded Stage-B V1 blueprint",
    )
    superseded_canonical = _validate_seal(
        superseded_root, label="superseded Stage-B V1 blueprint"
    )
    if (
        contract.sha256(superseded_payload) != SUPERSEDED_V1_BLUEPRINT_FILE_SHA256
        or superseded_root.get("blueprint_id") != SUPERSEDED_V1_BLUEPRINT_ID
        or superseded_canonical != SUPERSEDED_V1_BLUEPRINT_CANONICAL_SHA256
    ):
        raise StageBFacadeContractError("superseded Stage-B V1 blueprint differs")

    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "classification": CLASSIFICATION,
        "blueprint_file": str(output_path),
        "supersedes": {
            "path": str(superseded_path),
            "bytes": len(superseded_payload),
            "sha256": contract.sha256(superseded_payload),
            "blueprint_id": superseded_root["blueprint_id"],
            "canonical_sha256": superseded_canonical,
            "prior_schema_version": 1,
            "prior_kind": (
                "mf1750-ec5-h3-c-first-stage-b-read-only-facade-blueprint-v1"
            ),
            "prior_artifact_was_live_authorization": False,
            "prior_artifact_is_eligible_as_live_authority_base": False,
            "reason": (
                "overclaimed version identity promotion and used an incomplete "
                "legacy subset response validator"
            ),
        },
        "plan_binding": {
            "path": str(plan_path),
            "bytes": len(plan_payload),
            "sha256": contract.sha256(plan_payload),
            "canonical_sha256": plan_summary["canonical_sha256"],
            "plan_id": plan_summary["plan_id"],
            "release_id": plan_summary["release_id"],
            "firmware_binary_sha256": plan_summary["firmware_binary_sha256"],
            "stage_a_intent_canonical_sha256": plan_summary[
                "stage_a_new_boot_intent_sha256"
            ],
            "stage_b_intent_template_canonical_sha256": plan_summary[
                "stage_b_diagnostic_intent_template_sha256"
            ],
        },
        "stage_a_partial_receipt_binding": {
            "path": str(receipt_path),
            "bytes": len(receipt_payload),
            "sha256": contract.sha256(receipt_payload),
            "canonical_sha256": receipt_summary["canonical_sha256"],
            "receipt_id": receipt_summary["receipt_id"],
            "classification": receipt_summary["classification"],
            "stage_a_intent_satisfied": False,
            "active_application_boot_proven": False,
            "active_v10_proven": False,
            "candidate_ip_proven": False,
            "stage_b_authorization_derivable_from_receipt": False,
        },
        "authority_boundary": {
            "partial_receipt_is_stage_a_completion": False,
            "partial_receipt_satisfies_existing_sealed_boot_receipt_gate": False,
            "existing_plan_stage_order_is_satisfied": False,
            "existing_plan_trusted_single_ip_gate_is_satisfied": False,
            "existing_plan_allows_stage_b_authorization_now": False,
            "explicit_superseding_contract_required": True,
            "superseding_contract_must_authorize_only_version_conformance_bootstrap": True,
            "blueprint_is_that_superseding_contract": False,
            "blueprint_is_user_authorization": False,
            "copyable_authorization_token_emitted": False,
            "live_execution_entry_point_present": False,
            "execution_ready": False,
            "live_authorized": False,
        },
        "candidate_origin_policy": {
            "operator_selected_candidate_base_url": base_url,
            "candidate_source": plan["network_locator"]["observation_source"],
            "arp_cache_is_identity_proof": False,
            "arp_cache_is_reachability_proof": False,
            "arp_cache_is_fresh_boot_proof": False,
            "candidate_origin_trusted_before_version": False,
            "network_scan_allowed": False,
            "fallback_origin_allowed": False,
            "redirect_allowed": False,
            "dns_allowed": False,
            "first_exact_version_may_unlock_remaining_get_budget": True,
            "unlock_requires_source_pinned_exact_v10_version_validator_success": True,
            "successful_version_validation_classification": (
                "V10_PROTOCOL_RESPONSE_CONFORMANCE"
            ),
            "responder_or_device_identity_proven": False,
            "trusted_ip_binding_proven": False,
            "fresh_post_reset_application_boot_proven": False,
            "active_application_proven": False,
            "active_ota_slot_proven": False,
            "firmware_at_0x10000_is_running_proven": False,
            "unlock_policy_requires_explicit_superseding_contract": True,
        },
        "future_live_artifact_contracts": {
            "fresh_onsite_gate_receipt": {
                "required": True,
                "present": False,
                "must_bind_blueprint_id": True,
                "must_bind_selected_candidate_base_url": base_url,
                "j2_required": "OFF",
                "screen_required": recovery.SCREEN_STATE,
                "temperature_c_required": "25.0",
                "supply_required": "3.3V_CV_NORMAL",
                "current_limit_a_required": "1.0",
                "fresh_exact_current_reading_required": True,
                "monitoring_required": recovery.MONITORING_CONFIRMATION,
                "physical_cutoff_required": True,
                "no_refresh_or_wiring_change_since_stage_a_required": True,
            },
            "separate_stage_b_user_authorization": {
                "required": True,
                "present": False,
                "must_bind_blueprint_id": True,
                "must_bind_fresh_onsite_gate_canonical_sha256": True,
                "must_bind_superseding_contract_canonical_sha256": True,
                "must_bind_selected_candidate_base_url": base_url,
                "must_bind_planned_output": str(live_output),
                "must_bind_exact_order_and_budgets": True,
                "prior_stage_a_authorization_reusable": False,
            },
            "explicit_superseding_contract": {
                "required": True,
                "present": False,
                "must_preserve_partial_stage_a_classification": True,
                "may_authorize_only_first_version_get_for_protocol_conformance": True,
                "must_stop_permanently_if_version_or_validation_fails": True,
                "may_release_remaining_three_gets_only_after_version_validation": True,
                "must_not_claim_responder_device_ip_boot_or_active_app_identity": True,
            },
            "terminal_live_receipt": {
                "required": True,
                "present": False,
                "one_ordered_outcome_per_attempted_endpoint_required": True,
                "attempt_recorded_before_transport_send": True,
                "per_endpoint_required_fields": [
                    "ordinal",
                    "method",
                    "path",
                    "absolute_url",
                    "attempted",
                    "response_received",
                    "http_status",
                    "raw_body_bytes",
                    "raw_body_sha256",
                    "strict_parsed_canonical_sha256",
                    "validation_outcome",
                ],
                "raw_body_length_and_sha256_required_if_received": True,
                "strict_parsed_canonical_sha256_required_if_decode_succeeds": True,
                "transport_exception_wire_emission_classification": "UNKNOWN",
                "transport_exception_peer_receipt_classification": "UNKNOWN",
                "transport_exception_must_not_claim_exact_get_reached_device": True,
            },
        },
        "one_shot_output_contract": {
            "planned_live_output": str(live_output),
            "must_be_absent_before_attempt": True,
            "reservation": "O_EXCL_OPEN_BEFORE_FIRST_GET",
            "held_file_identity_must_be_verified": True,
            "reservation_is_attempt_consumption": True,
            "every_post_reservation_failure_is_terminal": True,
            "retry_allowed": False,
            "fallback_allowed": False,
            "automatic_recovery_allowed": False,
            "automatic_chaining_allowed": False,
        },
        "read_only_state_machine": {
            "selected_base_url": base_url,
            "ordered_requests": absolute,
            "successful_exact_get_count": 4,
            "maximum_get_count": 4,
            "maximum_post_count": 0,
            "request_body_count": 0,
            "claim_count": 0,
            "client_persistent_flash_or_nvs_mutation_requests": 0,
            "client_diagnostic_api_mutation_requests": 0,
            "client_visible_refresh_requests": 0,
            "actual_device_or_background_persistent_mutations": (
                "UNKNOWN_NOT_OBSERVED_BY_READ_ONLY_CLIENT"
            ),
            "actual_device_diagnostic_side_effects": (
                "UNKNOWN_NOT_OBSERVED_BY_READ_ONLY_CLIENT"
            ),
            "actual_device_visible_refreshes": (
                "UNKNOWN_NOT_OBSERVED_BY_READ_ONLY_CLIENT"
            ),
            "validate_each_response_before_next_request": True,
            "stop_on_first_transport_http_decode_or_validation_error": True,
            "retry": False,
            "fallback": False,
            "automatic_recovery": False,
            "automatic_chaining": False,
        },
        "frozen_v10_validator_binding": {
            **validator_binding,
            "release_file": plan["v10_release"]["path"],
            "release_id": plan_summary["release_id"],
            "ordinal": recovery.EXPECTED_ORDINAL,
            "legacy_subset_validator_names": list(FROZEN_VALIDATOR_NAMES),
            "legacy_version_subset_validator_is_source_incompatible": True,
            "legacy_version_subset_validator_called": False,
            "legacy_subset_validators_called_for": [
                "manifest",
                "status",
                "report",
            ],
            "legacy_host_bundle_recovery_diagnostic_compatible": False,
            "legacy_host_bundle_superseded_for_recovery_diagnostic": True,
            "fetch_all_then_validate_allowed": False,
        },
        "exact_response_surface_validation": {
            "strategy": (
                "source_pinned_exact_surface_with_legacy_subset_where_non_contradictory"
            ),
            "version_strategy": (
                "source_pinned_exact_surface_only_legacy_subset_source_incompatible"
            ),
            "manifest_status_report_strategy": (
                "frozen_subset_validator_plus_new_exact_surface_validator"
            ),
            "root_and_nested_exact_key_sets_required": True,
            "recursive_exact_json_types_required": True,
            "recursive_exact_values_required": True,
            "bool_is_not_accepted_as_int": True,
            "extra_keys_rejected": True,
            "missing_keys_rejected": True,
            "duplicate_json_keys_rejected_by_decoder": True,
            "nan_and_infinity_rejected_by_decoder": True,
            "trailing_json_rejected_by_decoder": True,
            "non_utf8_rejected_by_decoder": True,
            "non_object_root_rejected_by_decoder": True,
            "legacy_read_preflight_fetch_all_then_validate_forbidden": True,
            "legacy_get_predecoded_mapping_path_forbidden": True,
            "future_live_transport_must_supply_raw_response_bytes": True,
            "each_raw_response_must_decode_and_validate_before_next_get": True,
            "single_raw_decode_and_validate_api": (
                "decode_and_validate_v10_response_bytes"
            ),
            "raw_response_size_max_bytes": MAX_JSON_BYTES,
            "source_bindings": exact_surface_sources,
            "reference_only_inputs": {"wf20_25_generated_profile": reference_profile},
        },
        "implementation_surface": {
            "offline_only": True,
            "scripted_fake_requester_exact_type_and_raw_bytes_only": True,
            "fake_runner_cannot_write_planned_live_output": True,
            "http_client_implemented": False,
            "serial_or_com_client_implemented": False,
            "subprocess_client_implemented": False,
            "cli_surface": "OFFLINE_BUILD_AND_VALIDATE_ONLY",
            "live_run_or_execute_subcommand_implemented": False,
            "device_io_performed": False,
        },
        "unsatisfied_live_gates": [
            "explicit_superseding_contract_for_partial_stage_a_version_conformance_bootstrap",
            "fresh_onsite_gate_receipt",
            "separate_stage_b_user_authorization",
            "reviewed_live_transport_facade",
            "o_excl_live_attempt_reservation",
        ],
    }
    unsigned["blueprint_id"] = contract.sha256(unsigned)
    return _seal(unsigned)


def validate_blueprint(
    root: Mapping[str, Any], *, require_live_output_absent: bool = True
) -> dict[str, Any]:
    """Deep-validate the blueprint; never perform device I/O."""

    canonical = _validate_seal(root, label="Stage-B facade blueprint")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != KIND
        or root.get("classification") != CLASSIFICATION
    ):
        raise StageBFacadeContractError(
            "Stage-B facade blueprint schema/kind/classification differs"
        )
    plan_binding = root.get("plan_binding")
    receipt_binding = root.get("stage_a_partial_receipt_binding")
    if not isinstance(plan_binding, Mapping) or not isinstance(
        receipt_binding, Mapping
    ):
        raise StageBFacadeContractError("blueprint input bindings are absent")
    rebuilt = materialize_blueprint(
        plan_file=Path(str(plan_binding["path"])),
        stage_a_receipt_file=Path(str(receipt_binding["path"])),
        blueprint_file=Path(str(root["blueprint_file"])),
        _require_live_output_absent=require_live_output_absent,
    )
    if contract.canonical_json_bytes(root) != contract.canonical_json_bytes(rebuilt):
        raise StageBFacadeContractError(
            "Stage-B facade blueprint differs from deterministic reconstruction"
        )
    expected_id = contract.sha256(
        {
            key: value
            for key, value in root.items()
            if key not in {"blueprint_id", "integrity"}
        }
    )
    if root.get("blueprint_id") != expected_id:
        raise StageBFacadeContractError("Stage-B facade blueprint ID differs")
    live_output = Path(str(root["one_shot_output_contract"]["planned_live_output"]))
    if require_live_output_absent and live_output.exists():
        raise StageBFacadeContractError(
            "planned live output already exists; the one-shot attempt is consumed"
        )
    return {
        "valid": True,
        "blueprint_id": root["blueprint_id"],
        "canonical_sha256": canonical,
        "classification": CLASSIFICATION,
        "stage_a_intent_satisfied": False,
        "candidate_origin_trusted_before_version": False,
        "version_protocol_conformance_unlock_requires_superseding_contract": True,
        "version_validator_strategy": (
            "source_pinned_exact_surface_only_legacy_subset_source_incompatible"
        ),
        "remaining_validator_strategy": (
            "frozen_subset_validator_plus_new_exact_surface_validator"
        ),
        "legacy_host_bundle_recovery_diagnostic_compatible": False,
        "execution_ready": False,
        "live_authorized": False,
        "copyable_authorization_token_emitted": False,
        "live_execution_entry_point_present": False,
        "device_io_performed_by_validator": False,
        "unsatisfied_live_gates": list(root["unsatisfied_live_gates"]),
    }


def load_blueprint(path: Path) -> Mapping[str, Any]:
    _, _, root = _read_json(path, label="Stage-B facade blueprint")
    return root


def write_new_blueprint(path: Path, root: Mapping[str, Any]) -> None:
    validate_blueprint(root, require_live_output_absent=True)
    target = Path(os.path.abspath(os.fspath(path)))
    if target != Path(str(root["blueprint_file"])):
        raise StageBFacadeContractError("blueprint output self-path differs")
    parent = _assert_directory_chain(
        target.parent, create=True, label="blueprint output"
    )
    target = parent / target.name
    payload = contract.canonical_json_bytes(root) + b"\n"
    try:
        with target.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise StageBFacadeContractError("blueprint output already exists") from error
    except OSError as error:
        raise StageBFacadeContractError(
            f"could not write blueprint output: {error}"
        ) from error


@dataclass(frozen=True)
class ScriptedFakeResponse:
    """One in-memory response; it has no socket or URL-opening capability."""

    status: int
    body: bytes


class ScriptedFakeRequester:
    """Exact ordered fake that requires validation acknowledgement per response."""

    def __init__(self, script: Sequence[tuple[str, ScriptedFakeResponse]]) -> None:
        self._script: list[tuple[str, ScriptedFakeResponse]] = []
        for absolute_url, response in script:
            if (
                type(absolute_url) is not str
                or type(response) is not ScriptedFakeResponse
            ):
                raise StageBFacadeContractError("fake script item type differs")
            if type(response.status) is not int or type(response.body) is not bytes:
                raise StageBFacadeContractError("fake response type differs")
            self._script.append(
                (
                    absolute_url,
                    ScriptedFakeResponse(
                        status=response.status,
                        body=response.body,
                    ),
                )
            )
        self._cursor = 0
        self._unvalidated_url: str | None = None
        self.calls: list[dict[str, Any]] = []
        self.validation_acknowledgements: list[str] = []

    def fetch(
        self,
        *,
        method: str,
        absolute_url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> ScriptedFakeResponse:
        if self._unvalidated_url is not None:
            raise StageBFacadeContractError(
                "fake attempted a next request before validating the prior response"
            )
        if method != "GET" or body is not None:
            raise StageBFacadeContractError("fake facade permits bodyless GET only")
        if dict(headers) != {"Accept": "application/json"}:
            raise StageBFacadeContractError("fake request headers differ")
        if self._cursor >= len(self._script):
            raise StageBFacadeContractError("fake request exceeded scripted budget")
        expected_url, response = self._script[self._cursor]
        if absolute_url != expected_url:
            raise StageBFacadeContractError(
                "fake request origin/order differs from the sealed blueprint"
            )
        self._cursor += 1
        self._unvalidated_url = absolute_url
        self.calls.append(
            {
                "ordinal": self._cursor,
                "method": method,
                "absolute_url": absolute_url,
                "headers": dict(headers),
                "body": None,
            }
        )
        return response

    def acknowledge_validation(self, absolute_url: str) -> None:
        if self._unvalidated_url != absolute_url:
            raise StageBFacadeContractError(
                "fake validation acknowledgement does not match outstanding response"
            )
        self.validation_acknowledgements.append(absolute_url)
        self._unvalidated_url = None


class _FakeOutputReservation:
    def __init__(
        self,
        *,
        path: Path,
        handle: BinaryIO,
        identity: tuple[int, int],
        reservation: Mapping[str, Any],
    ) -> None:
        self.path = path
        self.handle = handle
        self.identity = identity
        self.reservation = dict(reservation)

    def _assert_identity(self) -> None:
        _assert_directory_chain(
            self.path.parent, create=False, label="fake result output"
        )
        try:
            path_info = self.path.lstat()
            held_info = os.fstat(self.handle.fileno())
        except OSError as error:
            raise StageBFacadeContractError(
                f"fake result output identity could not be verified: {error}"
            ) from error
        if (
            stat.S_ISLNK(path_info.st_mode)
            or not stat.S_ISREG(path_info.st_mode)
            or not stat.S_ISREG(held_info.st_mode)
            or (path_info.st_dev, path_info.st_ino) != self.identity
            or (held_info.st_dev, held_info.st_ino) != self.identity
        ):
            raise StageBFacadeContractError("fake result output identity changed")

    def finalize(self, root: Mapping[str, Any]) -> None:
        payload = contract.canonical_json_bytes(root) + b"\n"
        self._assert_identity()
        try:
            self.handle.seek(0)
            self.handle.truncate(0)
            self.handle.write(payload)
            self.handle.flush()
            os.fsync(self.handle.fileno())
        except OSError as error:
            raise StageBFacadeContractError(
                f"could not finalize fake result output: {error}"
            ) from error
        self._assert_identity()

    def close(self) -> None:
        self.handle.close()


def _reserve_fake_output(
    path: Path, *, blueprint: Mapping[str, Any]
) -> _FakeOutputReservation:
    target = Path(os.path.abspath(os.fspath(path)))
    live_output = Path(
        str(blueprint["one_shot_output_contract"]["planned_live_output"])
    )
    if target == live_output:
        raise StageBFacadeContractError(
            "fake runner is forbidden from writing the planned live output"
        )
    if not target.name.endswith(".fake-only.json"):
        raise StageBFacadeContractError(
            "fake result output must end with '.fake-only.json'"
        )
    parent = _assert_directory_chain(
        target.parent, create=True, label="fake result output"
    )
    target = parent / target.name
    try:
        handle = target.open("xb+", buffering=0)
        created = os.fstat(handle.fileno())
        identity = (created.st_dev, created.st_ino)
    except FileExistsError as error:
        raise StageBFacadeContractError(
            "fake result output already exists; no retry is allowed"
        ) from error
    except OSError as error:
        raise StageBFacadeContractError(
            f"could not reserve fake result output: {error}"
        ) from error
    try:
        reservation = _seal(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": FAKE_RESULT_KIND,
                "classification": FAKE_RESULT_CLASSIFICATION,
                "state": "RESERVED_FAKE_ONLY_ATTEMPT_CONSUMED",
                "output_file": str(target),
                "blueprint_id": blueprint["blueprint_id"],
                "created_before_fake_requests": True,
                "retry_allowed": False,
                "device_io_performed": False,
            }
        )
        reservation_object = _FakeOutputReservation(
            path=target,
            handle=handle,
            identity=identity,
            reservation=reservation,
        )
        reservation_object.finalize(reservation)
        return reservation_object
    except Exception:
        if "handle" in locals() and not handle.closed:
            handle.close()
        raise


def _fake_result(
    *,
    blueprint: Mapping[str, Any],
    reservation: _FakeOutputReservation,
    state: str,
    requester: ScriptedFakeRequester,
    validated_names: Sequence[str],
    validation_stack_outcomes: Sequence[Mapping[str, Any]],
    boot_nonce: str | None,
    version_protocol_conformance_validated: bool,
    error: Exception | None,
) -> dict[str, Any]:
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": FAKE_RESULT_KIND,
        "classification": FAKE_RESULT_CLASSIFICATION,
        "state": state,
        "output_file": str(reservation.path),
        "blueprint_id": blueprint["blueprint_id"],
        "blueprint_canonical_sha256": blueprint["integrity"]["canonical_sha256"],
        "selected_base_url": blueprint["read_only_state_machine"]["selected_base_url"],
        "requests_attempted": len(requester.calls),
        "request_log": deepcopy(requester.calls),
        "validated_response_names": list(validated_names),
        "validation_stack_outcomes": deepcopy(list(validation_stack_outcomes)),
        "validation_acknowledgements": list(requester.validation_acknowledgements),
        "validate_each_response_before_next_request": True,
        "version_protocol_conformance_simulated": (
            version_protocol_conformance_validated
        ),
        "version_validation_classification": (
            "V10_PROTOCOL_RESPONSE_CONFORMANCE"
            if version_protocol_conformance_validated
            else "NOT_VALIDATED"
        ),
        "version_validation_is_responder_or_device_identity_proof": False,
        "version_validation_is_trusted_ip_proof": False,
        "version_validation_is_fresh_boot_or_active_app_proof": False,
        "boot_nonce": boot_nonce,
        "get_requests": len(requester.calls),
        "post_requests": 0,
        "request_bodies": 0,
        "claims": 0,
        "client_persistent_flash_or_nvs_mutation_requests": 0,
        "client_diagnostic_api_mutation_requests": 0,
        "client_visible_refresh_requests": 0,
        "actual_device_side_effects": "NOT_APPLICABLE_FAKE_ONLY_NO_DEVICE_IO",
        "fallbacks": 0,
        "retries": 0,
        "automatic_recoveries": 0,
        "automatic_chains": 0,
        "network_requests": 0,
        "serial_or_com_accesses": 0,
        "subprocesses": 0,
        "hardware_accessed": False,
        "device_io_performed": False,
        "planned_live_output_touched": False,
        "retry_allowed": False,
    }
    if error is None:
        unsigned.update(
            {
                "outcome": "FAKE_VALIDATOR_STATE_MACHINE_COMPLETE",
                "error_type": None,
                "error": None,
                "failed_endpoint": None,
            }
        )
    else:
        failed_index = max(0, min(len(requester.calls) - 1, 3))
        next_request = blueprint["read_only_state_machine"]["ordered_requests"][
            failed_index
        ]
        unsigned.update(
            {
                "outcome": "TERMINAL_FAKE_ONLY_FAILURE_NO_RETRY",
                "error_type": type(error).__name__,
                "error": str(error),
                "failed_endpoint": next_request["path"],
            }
        )
    return _seal(unsigned)


def run_scripted_fake_only(
    blueprint: Mapping[str, Any],
    *,
    requester: ScriptedFakeRequester,
    fake_output: Path,
) -> dict[str, Any]:
    """Exercise strict sequencing with an exact in-memory fake only.

    The exact-type check is intentional: callers cannot inject a network
    callable.  The output is permanently marked synthetic and cannot use the
    plan's live diagnostic path.
    """

    validate_blueprint(blueprint, require_live_output_absent=True)
    if type(requester) is not ScriptedFakeRequester:
        raise StageBFacadeContractError(
            "fake runner accepts the exact ScriptedFakeRequester type only"
        )
    reservation = _reserve_fake_output(fake_output, blueprint=blueprint)
    validated: list[str] = []
    validation_stack_outcomes: list[dict[str, Any]] = []
    boot_nonce: str | None = None
    version_protocol_conformance_validated = False
    error: Exception | None = None
    try:
        try:
            release_file = Path(
                str(blueprint["frozen_v10_validator_binding"]["release_file"])
            )
            context = _load_frozen_v10_release(release_file)
            machine = blueprint["read_only_state_machine"]
            ordered = machine["ordered_requests"]
            if len(ordered) != 4:
                raise StageBFacadeContractError("fake request budget differs")
            for name, request in zip(ENDPOINT_NAMES, ordered, strict=True):
                response = requester.fetch(
                    method="GET",
                    absolute_url=str(request["absolute_url"]),
                    headers={"Accept": "application/json"},
                    body=None,
                )
                if response.status != 200:
                    raise StageBFacadeContractError(
                        f"GET {request['path']} returned HTTP {response.status}"
                    )
                stack = (
                    [
                        "raw_size_and_strict_json_decoder",
                        "source_pinned_exact_surface_validator",
                    ]
                    if name == "version"
                    else [
                        "raw_size_and_strict_json_decoder",
                        "frozen_subset_validator",
                        "source_pinned_exact_surface_validator",
                    ]
                )
                stack_record = {
                    "ordinal": request["ordinal"],
                    "response_name": name,
                    "validator_stack": stack,
                    "legacy_version_subset_invoked": False,
                    "outcome": "STARTED",
                }
                validation_stack_outcomes.append(stack_record)
                try:
                    _, observed_nonce = decode_and_validate_v10_response_bytes(
                        name,
                        response.body,
                        context,
                        recovery.EXPECTED_ORDINAL,
                    )
                except Exception:
                    stack_record["outcome"] = "FAILED_TERMINAL"
                    raise
                stack_record["outcome"] = "PASS"
                if name == "version":
                    version_protocol_conformance_validated = True
                elif name == "status":
                    boot_nonce = observed_nonce
                requester.acknowledge_validation(str(request["absolute_url"]))
                validated.append(name)
        except (
            Exception
        ) as caught:  # terminalize every ordinary post-reservation failure
            error = caught
        state = (
            "COMPLETE_FAKE_ONLY_VALIDATION"
            if error is None
            else "TERMINAL_FAKE_ONLY_FAILURE"
        )
        result = _fake_result(
            blueprint=blueprint,
            reservation=reservation,
            state=state,
            requester=requester,
            validated_names=validated,
            validation_stack_outcomes=validation_stack_outcomes,
            boot_nonce=boot_nonce,
            version_protocol_conformance_validated=(
                version_protocol_conformance_validated
            ),
            error=error,
        )
        reservation.finalize(result)
        return result
    finally:
        reservation.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", allow_abbrev=False)
    build.add_argument("--plan", type=Path, required=True)
    build.add_argument("--stage-a-receipt", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--blueprint", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Build or validate offline evidence; never expose fake or live execution."""

    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            root = materialize_blueprint(
                plan_file=args.plan,
                stage_a_receipt_file=args.stage_a_receipt,
                blueprint_file=args.output,
            )
            write_new_blueprint(args.output, root)
        else:
            root = load_blueprint(args.blueprint)
        summary = validate_blueprint(root, require_live_output_absent=True)
        summary["blueprint_file"] = str(
            Path(
                os.path.abspath(
                    os.fspath(
                        args.output if args.command == "build" else args.blueprint
                    )
                )
            )
        )
    except (StageBFacadeContractError, KeyError, TypeError) as error:
        print(f"Stage-B facade blueprint error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
