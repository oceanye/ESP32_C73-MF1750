#!/usr/bin/env python3
"""Physical-once gate for one exact empirical-H3 profile release.

``describe`` and diagnostic-bound ``authorize`` are offline; ``diagnose`` is
GET-only.  ``run`` creates a permanent O_EXCL host claim before its first
network request, sends exactly one bodyless ARM POST and one bodyless EXECUTE
POST, then uses bounded GET-only report polling.  There is no retry, automatic
recovery, action chaining, profile switch, firmware flashing, serial access,
or raw payload ingress.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import ipaddress
import json
import math
from numbers import Real
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import (
    Any,
    BinaryIO,
    Callable,
    Final,
    Mapping,
    NamedTuple,
    Protocol,
    Sequence,
)
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from tools import mf1750_ec5_eightcode_atlas as atlas
from tools import mf1750_ec5_runtime_lut_contract as contract
from tools import mf1750_ec5_runtime_lut_release as release


SCHEMA_VERSION: Final = 1
DIAGNOSTIC_KIND: Final = "mf1750-ec5-empirical-h3-j2-off-diagnostic"
CLAIM_KIND: Final = "mf1750-ec5-empirical-h3-permanent-host-claim"
RESULT_KIND: Final = "mf1750-ec5-empirical-h3-physical-once-result"
OFFLINE_AUTHORIZATION_KIND: Final = (
    "mf1750-ec5-empirical-h3-offline-authorization-token"
)
OUTPUT_ATTEMPT_KIND: Final = "mf1750-ec5-empirical-h3-output-attempt"
DEFAULT_CLAIM_REGISTRY: Final = (
    contract.REPO_ROOT / ".test-output" / "hardware" / ".mf1750_ec5_empirical_h3_claims"
)
DEFAULT_POLL_COUNT: Final = 60
DEFAULT_POLL_INTERVAL_SECONDS: Final = 1.0
POST_EXECUTE_SETTLE_SECONDS: Final = 30.0
MAX_JSON_BYTES: Final = 4_000_000
BOOT_NONCE = re.compile(r"^[0-9a-f]{16}$")
ARM_NONCE = re.compile(r"^[0-9a-f]{16}$")
SCREEN_INITIAL = "clean_white"
SCREEN_RECOVERY = "post_runtime_unrecovered"


class PhysicalOnceError(RuntimeError):
    """A safety gate failed before mutation or before a known terminal result."""


class PhysicalOnceUnknown(PhysicalOnceError):
    """The claim is consumed, so retry is permanently forbidden."""


class HttpResponse(NamedTuple):
    status: int
    body: Mapping[str, Any]


class OutputReservation:
    """An O_EXCL evidence sink held open across one diagnostic or action."""

    def __init__(
        self,
        path: Path,
        handle: BinaryIO,
        identity: tuple[int, int],
        reservation: Mapping[str, Any],
        *,
        label: str,
    ) -> None:
        self.path = path
        self.handle = handle
        self.identity = identity
        self.reservation = dict(reservation)
        self.label = label
        self.finalized = False

    def _assert_identity(self) -> None:
        _require_non_symlink_directory_chain(self.path.parent, create=False)
        try:
            path_info = self.path.lstat()
            held_info = os.fstat(self.handle.fileno())
        except OSError as error:
            raise PhysicalOnceError(
                f"{self.label} path identity could not be verified: {error}"
            ) from error
        if (
            stat.S_ISLNK(path_info.st_mode)
            or not stat.S_ISREG(path_info.st_mode)
            or not stat.S_ISREG(held_info.st_mode)
            or (path_info.st_dev, path_info.st_ino) != self.identity
            or (held_info.st_dev, held_info.st_ino) != self.identity
        ):
            raise PhysicalOnceError(f"{self.label} path identity changed")

    def _replace_through_held_handle(self, value: Mapping[str, Any]) -> None:
        payload = contract.canonical_json_bytes(value) + b"\n"
        self._assert_identity()
        try:
            self.handle.seek(0)
            self.handle.truncate(0)
            self.handle.write(payload)
            self.handle.flush()
            os.fsync(self.handle.fileno())
        except OSError as error:
            raise PhysicalOnceError(
                f"could not finalize {self.label}: {error}"
            ) from error
        self._assert_identity()
        if os.fstat(self.handle.fileno()).st_size != len(payload):
            raise PhysicalOnceError(f"{self.label} final size differs")
        self.finalized = True

    def finalize(self, value: Mapping[str, Any]) -> None:
        self._replace_through_held_handle(value)

    def finalize_failure(
        self, error: BaseException, *, claim_may_be_consumed: bool
    ) -> None:
        failure = _seal(
            {
                **{
                    key: value
                    for key, value in self.reservation.items()
                    if key != "integrity"
                },
                "state": (
                    "TERMINAL_UNKNOWN_CLAIM_MAY_BE_CONSUMED"
                    if claim_may_be_consumed
                    else "TERMINAL_PRECLAIM_FAILURE"
                ),
                "error_type": type(error).__name__,
                "error": str(error),
                "retry_allowed": False,
                "network_requests_after_reservation": "unknown_or_not_applicable",
            }
        )
        self._replace_through_held_handle(failure)

    def close(self) -> None:
        self.handle.close()


class Requester(Protocol):
    def __call__(
        self, method: str, endpoint: str, headers: Mapping[str, str]
    ) -> HttpResponse: ...


@dataclass(frozen=True)
class ReleaseContext:
    root: Mapping[str, Any]
    release_file: Path | None = None

    @property
    def profile_id(self) -> str:
        return str(self.root["profile_id"])

    @property
    def release_id(self) -> str:
        return str(self.root["release_id"])

    def action(self, ordinal: int) -> Mapping[str, Any]:
        matches = [
            item
            for item in self.root["profile_contract"]["actions"]
            if item["ordinal"] == ordinal
        ]
        if len(matches) != 1:
            raise PhysicalOnceError(f"release has no unique ordinal {ordinal}")
        return matches[0]

    def binding(self, ordinal: int) -> Mapping[str, Any]:
        matches = [
            item
            for item in self.root["action_artifact_bindings"]
            if item["ordinal"] == ordinal
        ]
        if len(matches) != 1:
            raise PhysicalOnceError(f"release has no unique binding {ordinal}")
        return matches[0]


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    root = dict(unsigned)
    root["integrity"] = {
        "algorithm": "sha256",
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
        "canonical_sha256": contract.sha256(root),
    }
    return root


def _validate_seal(value: Mapping[str, Any], *, label: str) -> str:
    integrity = value.get("integrity")
    if not isinstance(integrity, Mapping):
        raise PhysicalOnceError(f"{label} is not sealed")
    expected = _seal({key: item for key, item in value.items() if key != "integrity"})[
        "integrity"
    ]
    if dict(integrity) != expected:
        raise PhysicalOnceError(f"{label} integrity mismatch")
    return str(integrity["canonical_sha256"])


def context_from_root(root: Mapping[str, Any]) -> ReleaseContext:
    try:
        release.validate_release(root)
    except release.RuntimeLutReleaseError as error:
        raise PhysicalOnceError(f"release validation failed: {error}") from error
    return ReleaseContext(root=dict(root))


def load_release(path: Path) -> ReleaseContext:
    try:
        root = release.load_release(path)
    except release.RuntimeLutReleaseError as error:
        raise PhysicalOnceError(f"release validation failed: {error}") from error
    return ReleaseContext(root=root, release_file=Path(path).resolve())


def _temperature(
    value: str | float | int, context: ReleaseContext, ordinal: int
) -> str:
    try:
        decimal = Decimal(str(value))
    except InvalidOperation as error:
        raise PhysicalOnceError("operator temperature is not numeric") from error
    if not decimal.is_finite() or decimal != decimal.quantize(Decimal("0.1")):
        raise PhysicalOnceError("operator temperature must be a finite 0.1 C value")
    policy = context.action(ordinal)["temperature_policy"]
    interval_key = "allowed_c" if ordinal == 1 else "allowed_record_range_c"
    minimum, maximum = policy[interval_key]
    if decimal < Decimal(str(minimum)) or decimal > Decimal(str(maximum)):
        if ordinal == 1:
            raise PhysicalOnceError(
                f"operator temperature {decimal:.1f} C is outside the selected "
                f"experimental fixed guard {minimum:.1f}..{maximum:.1f} C; "
                "this guard is not a vendor temperature qualification"
            )
        raise PhysicalOnceError(
            f"factory-OTP recovery temperature record {decimal:.1f} C is outside "
            f"the existing observed-ceiling guard {minimum:.1f}..{maximum:.1f} C"
        )
    return f"{decimal:.1f}"


def required_authorization(
    context: ReleaseContext,
    ordinal: int,
    operator_temperature_c: str | float | int,
    diagnostic: Mapping[str, Any],
) -> str:
    action = context.action(ordinal)
    temperature = _temperature(operator_temperature_c, context, ordinal)
    boot_nonce = validate_diagnostic(
        context,
        ordinal,
        diagnostic,
        operator_temperature_c=temperature,
    )
    diagnostic_sha256 = str(diagnostic["integrity"]["canonical_sha256"])
    slug = temperature.replace("-", "M").replace(".", "P")
    assumptions = context.root["profile_contract"]["assumption_acceptance"][
        "canonical_sha256"
    ]
    monitoring = contract.sha256(
        contract.OPERATOR_MONITORING_CONFIRMATION.encode("ascii")
    )
    role = "H3_ATLAS" if ordinal == 1 else "OTP_WHITE"
    return (
        f"AUTHORIZE_V2_ONE_VISIBLE_EC5_{context.profile_id}_{role}_ORDINAL_{ordinal:02d}"
        f"__TEMP_C_{slug}__RELEASE_{context.release_id.upper()}"
        f"__ACTION_{action['hardware_action_id'].upper()}"
        f"__DESCRIPTOR_{action['transaction_descriptor_sha256'].upper()}"
        f"__DIAGNOSTIC_{diagnostic_sha256.upper()}"
        f"__BOOT_NONCE_{boot_nonce.upper()}"
        f"__ACCEPT_U1_U7_{assumptions.upper()}"
        f"__MONITORS_{monitoring.upper()}"
        "__NO_RETRY_NO_AUTO_RECOVERY_NO_AUTOCHAIN_NO_PROFILE_SWITCH"
    )


def offline_authorization(
    context: ReleaseContext,
    ordinal: int,
    *,
    selected_profile_id: str,
    operator_temperature_c: str | float | int,
    empirical_acceptance: str,
    operator_monitoring_state: str,
    diagnostic: Mapping[str, Any],
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    """Derive a token offline after exact operator acknowledgements."""

    if selected_profile_id != context.profile_id:
        raise PhysicalOnceError("selected profile differs from the exact release")
    if empirical_acceptance != contract.EMPIRICAL_ACCEPTANCE_PHRASE:
        raise PhysicalOnceError("exact U1-U7 empirical acceptance is absent")
    if operator_monitoring_state != contract.OPERATOR_MONITORING_CONFIRMATION:
        raise PhysicalOnceError("operator safety-monitoring confirmation differs")
    temperature = _temperature(operator_temperature_c, context, ordinal)
    token = required_authorization(context, ordinal, temperature, diagnostic)
    boot_nonce = str(diagnostic["boot_nonce"])
    diagnostic_sha256 = str(diagnostic["integrity"]["canonical_sha256"])
    if ordinal == 2:
        _require_runtime_claim(context, Path(claim_registry))
    acceptance = context.root["profile_contract"]["assumption_acceptance"]
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": OFFLINE_AUTHORIZATION_KIND,
            "profile_id": context.profile_id,
            "release_id": context.release_id,
            "ordinal": ordinal,
            "role": context.action(ordinal)["role"],
            "hardware_action_id": context.action(ordinal)["hardware_action_id"],
            "transaction_descriptor_sha256": context.action(ordinal)[
                "transaction_descriptor_sha256"
            ],
            "operator_temperature_c": temperature,
            "diagnostic_canonical_sha256": diagnostic_sha256,
            "boot_nonce": boot_nonce,
            "u1_u7": acceptance["assumptions"],
            "u1_u7_exact_phrase": empirical_acceptance,
            "u1_u7_acceptance_sha256": acceptance["canonical_sha256"],
            "acceptance_is_proof": False,
            "operator_monitoring_confirmation": operator_monitoring_state,
            "authorization_token": token,
            "offline": True,
            "claims_created": False,
            "network_requests": 0,
            "post_requests": 0,
            "device_io_performed": False,
            "visible_refreshes": 0,
            "live_authorized": False,
            "fresh_j2_off_diagnostic_and_all_run_gates_still_required": True,
        }
    )


def describe(context: ReleaseContext) -> dict[str, Any]:
    return {
        "profile_id": context.profile_id,
        "release_id": context.release_id,
        "vendor_filename_numeric_tokens": context.root["profile_contract"][
            "vendor_filename_numeric_tokens"
        ],
        "temperature_filename_semantics_proven": context.root["profile_contract"][
            "temperature_filename_semantics_proven"
        ],
        "experimental_fixed_temperature_guard_c": context.root["profile_contract"][
            "experimental_fixed_temperature_guard_c"
        ],
        "temperature_guard_basis": context.root["profile_contract"][
            "temperature_guard_basis"
        ],
        "requested_electrical_metadata": context.root["profile_contract"][
            "requested_electrical_metadata"
        ],
        "actions": [
            {
                "ordinal": ordinal,
                "role": context.action(ordinal)["role"],
                "base_route": context.binding(ordinal)["base_route"],
                "environment": context.binding(ordinal)["environment"],
                "nvs_namespace": context.binding(ordinal)["nvs_namespace"],
                "firmware_binary_sha256": context.binding(ordinal)[
                    "firmware_binary_sha256"
                ],
                "firmware_elf_sha256": context.binding(ordinal)["firmware_elf_sha256"],
                "independent_authorization_required": True,
            }
            for ordinal in (1, 2)
        ],
        "default_is_offline": True,
        "network_requests": 0,
        "post_requests": 0,
        "claims_created": False,
        "visible_refreshes": 0,
        "automatic_chaining": False,
        "automatic_recovery": False,
        "retry": False,
        "profile_switch": False,
    }


def _identity_expected(context: ReleaseContext, ordinal: int) -> dict[str, Any]:
    binding = context.binding(ordinal)
    return {
        "build_tag": binding["build_tag"],
        "test_id": binding["test_id"],
        "campaign_id": binding["campaign_id"],
        "environment": binding["environment"],
        "device_api_version": contract.DEVICE_API_VERSION,
        "contract_id": context.root["contract_id"],
        "transaction_descriptor_sha256": binding["transaction_descriptor_sha256"],
        "transaction_descriptor_marker": contract.compiled_descriptor_marker(
            context.profile_id, context.action(ordinal)["role"]
        ),
        "running_app_elf_sha256": binding["firmware_elf_sha256"],
    }


def _expect_identity(
    value: Mapping[str, Any], context: ReleaseContext, ordinal: int, *, label: str
) -> None:
    for key, expected in _identity_expected(context, ordinal).items():
        if value.get(key) != expected:
            raise PhysicalOnceError(f"{label} {key} identity differs")


def _get(
    requester: Requester, endpoint: str, *, headers: Mapping[str, str] | None = None
) -> Mapping[str, Any]:
    response = requester("GET", endpoint, headers or {})
    if response.status != 200:
        raise PhysicalOnceError(f"GET {endpoint} returned HTTP {response.status}")
    return response.body


def _expect_version(
    value: Mapping[str, Any], context: ReleaseContext, ordinal: int
) -> None:
    binding = context.binding(ordinal)
    action = context.action(ordinal)
    if value.get("schema_version") != 1 or value.get("kind") != (
        f"{binding['kind_prefix']}-version"
    ):
        raise PhysicalOnceError("device version schema/kind differs")
    _expect_identity(value, context, ordinal, label="version")
    profile = value.get("profile")
    if (
        not isinstance(profile, Mapping)
        or profile.get("profile_id") != context.profile_id
    ):
        raise PhysicalOnceError("device version profile differs")
    temperature_policy = action["temperature_policy"]
    interval_key = "allowed_c" if ordinal == 1 else "allowed_record_range_c"
    minimum, maximum = temperature_policy[interval_key]
    manifest_temperature_tokens = (
        context.root["profile_contract"]["vendor_filename_numeric_tokens"]
        if ordinal == 1
        else [minimum, maximum]
    )
    if (
        profile.get("compiled_profile_count") != 1
        or profile.get("auto_selected") is not False
        # These legacy device fields preserve the two opaque numeric filename
        # tokens.  They are deliberately no longer compared with the live
        # temperature guard or interpreted as a qualified interval.
        or profile.get("apparent_temperature_min_c")
        != int(manifest_temperature_tokens[0])
        or profile.get("apparent_temperature_max_c")
        != int(manifest_temperature_tokens[1])
        or value.get("action_count") != 1
        or value.get("startup_refresh") is not False
        or value.get("raw_ingress") is not False
        or value.get("retry") is not False
        or value.get("automatic_chaining") is not False
        or value.get("profile_switch") is not False
        or action["profile_id"] != context.profile_id
    ):
        raise PhysicalOnceError("device version safety/profile contract differs")
    if ordinal == 1 and (
        temperature_policy.get("kind")
        != "experimental_fixed_25_from_adjacent_legacy_selector"
        or temperature_policy.get("allowed_c") != [25.0, 25.0]
        or temperature_policy.get("vendor_filename_band_claim") is not False
        or temperature_policy.get("temperature_compatibility_qualified") is not False
        or context.root["profile_contract"].get("temperature_filename_semantics_proven")
        is not False
        or context.root["profile_contract"].get("temperature_compatibility_qualified")
        is not False
    ):
        raise PhysicalOnceError("experimental fixed-temperature guard differs")
    if ordinal == 2 and (
        profile.get("temperature_policy")
        != "factory_otp_existing_observed_ceiling_not_vendor_band"
        or profile.get("temperature_limit_is_safety_qualification") is not False
    ):
        raise PhysicalOnceError("recovery temperature policy is mislabeled")
    if ordinal == 1:
        wanted = context.root["profile_contract"]["requested_electrical_metadata"]
        observed = {
            "gate_positive_mv": profile.get("requested_gate_positive_mv"),
            "gate_negative_mv": profile.get("requested_gate_negative_mv"),
            "full_source_positive_mv": profile.get("requested_full_source_positive_mv"),
            "full_source_negative_mv": profile.get("requested_full_source_negative_mv"),
            "intermediate_source_mv": {
                "vsh_lv": profile.get("requested_vsh_lv_mv"),
                "vsl_lv": profile.get("requested_vsl_lv_mv"),
                "vsh_lv2": profile.get("requested_vsh_lv2_mv"),
                "vsl_lv2": profile.get("requested_vsl_lv2_mv"),
            },
            "frame_rate_hz": profile.get("requested_frame_rate_hz"),
            "vcom_written_or_swept": False,
            "panel_fpl_or_film_lot_qualified": profile.get(
                "panel_or_fpl_limits_proven"
            ),
        }
        if (
            observed != wanted
            or profile.get("electrical_values_source") != "generated_include_metadata"
            or profile.get("h3_header_binding_proven") is not False
        ):
            raise PhysicalOnceError("runtime requested electrical metadata differs")


def _expect_manifest(
    value: Mapping[str, Any], context: ReleaseContext, ordinal: int
) -> None:
    binding = context.binding(ordinal)
    action = context.action(ordinal)
    if value.get("schema_version") != 1 or value.get("kind") != (
        f"{binding['kind_prefix']}-manifest"
    ):
        raise PhysicalOnceError("device manifest schema/kind differs")
    _expect_identity(value, context, ordinal, label="manifest")
    actions = value.get("actions")
    expected_action = {
        "ordinal": ordinal,
        "role": action["role"],
        "descriptor_id": action["transaction_descriptor_sha256"],
        "action_id": action["hardware_action_id"],
        "frame_sha256": action["payload_identity"]["frame_sha256"],
        "cs1_dtm_sha256": action["payload_identity"]["cs1_dtm_sha256"],
        "cs2_dtm_sha256": action["payload_identity"]["cs2_dtm_sha256"],
    }
    if actions != [expected_action]:
        raise PhysicalOnceError("device manifest action differs")
    forbidden_true = (
        "startup_refresh",
        "raw_frame_ingress",
        "raw_lut_ingress",
        "electrical_parameter_ingress",
        "timing_parameter_ingress",
        "retry",
        "automatic_chaining",
        "profile_switch",
        "vcom_write",
        "vcom_sweep",
    )
    if any(value.get(key) is not False for key in forbidden_true):
        raise PhysicalOnceError("device manifest safety flags differ")
    if (
        value.get("action_count") != 1
        or value.get("one_driver_call_per_action") is not True
    ):
        raise PhysicalOnceError("device manifest action-count contract differs")
    assumptions = value.get("unproven_assumptions")
    if not isinstance(assumptions, list) or [
        item.get("id") for item in assumptions
    ] != [f"U{index}" for index in range(1, 8)]:
        raise PhysicalOnceError("device manifest U1-U7 acceptance surface differs")
    if any(item.get("status") != "unproven" for item in assumptions):
        raise PhysicalOnceError("device manifest mislabels an empirical assumption")


def _expect_status(
    value: Mapping[str, Any],
    context: ReleaseContext,
    ordinal: int,
    *,
    boot_nonce: str | None = None,
) -> str:
    binding = context.binding(ordinal)
    if value.get("schema_version") != 1 or value.get("kind") != (
        f"{binding['kind_prefix']}-status"
    ):
        raise PhysicalOnceError("device status schema/kind differs")
    _expect_identity(value, context, ordinal, label="status")
    observed_nonce = value.get("boot_nonce")
    if (
        not isinstance(observed_nonce, str)
        or BOOT_NONCE.fullmatch(observed_nonce) is None
    ):
        raise PhysicalOnceError("device boot nonce is invalid")
    if boot_nonce is not None and observed_nonce != boot_nonce:
        raise PhysicalOnceError("device rebooted after the J2-OFF diagnostic")
    if (
        value.get("profile_id") != context.profile_id
        or value.get("state") != "ready"
        or value.get("phase") != 0
        or value.get("phase_name") != "READY"
        or value.get("cursor_raw") != ordinal
        or value.get("next_ordinal") != ordinal
        or value.get("campaign_complete") is not False
        or value.get("fixture_self_check_passed") is not True
        or value.get("cursor_valid") is not True
        or value.get("persistent_key_present") is not False
        or value.get("execute_pending") is not False
        or value.get("arm_request_count") != 0
        or value.get("execute_request_count") != 0
        or value.get("total_driver_call_count") != 0
        or value.get("gpio_initialized") is not True
        or value.get("rst") != 0
        or value.get("cs") != 0
        or value.get("cs2") != 0
        or value.get("sck") != 0
        or value.get("dc") != 0
        or value.get("mosi") != 0
        or value.get("busy") not in (0, 1)
    ):
        raise PhysicalOnceError("device status is not the virgin ready state")
    return observed_nonce


def _expect_preflight_report(
    value: Mapping[str, Any], context: ReleaseContext, ordinal: int
) -> None:
    binding = context.binding(ordinal)
    if value.get("schema_version") != 1 or value.get("kind") != (
        f"{binding['kind_prefix']}-report"
    ):
        raise PhysicalOnceError("device preflight report schema/kind differs")
    _expect_identity(value, context, ordinal, label="preflight report")
    if (
        value.get("terminal_state") != "NOT_EXECUTED"
        or value.get("result") is not False
        or value.get("driver_called") is not False
        or value.get("driver_call_count_for_action") != 0
        or value.get("no_retry") is not True
    ):
        raise PhysicalOnceError("device preflight report is not virgin")


def _read_preflight(
    context: ReleaseContext,
    ordinal: int,
    requester: Requester,
    *,
    headers: Mapping[str, str] | None = None,
    boot_nonce: str | None = None,
) -> tuple[str, dict[str, Mapping[str, Any]]]:
    base = str(context.binding(ordinal)["base_route"])
    payloads = {
        name: _get(requester, f"{base}/{name}", headers=headers)
        for name in ("version", "manifest", "status", "report")
    }
    _expect_version(payloads["version"], context, ordinal)
    _expect_manifest(payloads["manifest"], context, ordinal)
    observed_nonce = _expect_status(
        payloads["status"], context, ordinal, boot_nonce=boot_nonce
    )
    _expect_preflight_report(payloads["report"], context, ordinal)
    return observed_nonce, payloads


def diagnose_j2_off(
    context: ReleaseContext,
    ordinal: int,
    *,
    operator_temperature_c: str | float | int,
    operator_screen_state: str,
    operator_j2_state: str,
    operator_monitoring_state: str,
    requester: Requester,
) -> dict[str, Any]:
    """Perform four GETs; J2 and screen state remain operator assertions."""

    temperature = _temperature(operator_temperature_c, context, ordinal)
    expected_screen = SCREEN_INITIAL if ordinal == 1 else SCREEN_RECOVERY
    if operator_j2_state != "OFF":
        raise PhysicalOnceError("J2-OFF diagnostic requires operator assertion OFF")
    if operator_monitoring_state != contract.OPERATOR_MONITORING_CONFIRMATION:
        raise PhysicalOnceError("operator safety-monitoring confirmation differs")
    if operator_screen_state != expected_screen:
        raise PhysicalOnceError(
            f"ordinal {ordinal} requires operator screen state {expected_screen!r}"
        )
    boot_nonce, _ = _read_preflight(context, ordinal, requester)
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": DIAGNOSTIC_KIND,
            "release_id": context.release_id,
            "profile_id": context.profile_id,
            "ordinal": ordinal,
            "role": context.action(ordinal)["role"],
            "hardware_action_id": context.action(ordinal)["hardware_action_id"],
            "firmware_binary_sha256": context.binding(ordinal)[
                "firmware_binary_sha256"
            ],
            "firmware_elf_sha256": context.binding(ordinal)["firmware_elf_sha256"],
            "transaction_descriptor_sha256": context.binding(ordinal)[
                "transaction_descriptor_sha256"
            ],
            "boot_nonce": boot_nonce,
            "operator_temperature_c": temperature,
            "operator_j2_assertion": "OFF",
            "j2_is_device_measured": False,
            "operator_monitoring_state": operator_monitoring_state,
            "operator_screen_state": operator_screen_state,
            "get_requests": 4,
            "post_requests": 0,
            "claim_created": False,
            "device_mutation_performed": False,
            "visible_refreshes": 0,
        }
    )


def validate_diagnostic(
    context: ReleaseContext,
    ordinal: int,
    diagnostic: Mapping[str, Any],
    *,
    operator_temperature_c: str | float | int,
) -> str:
    _validate_seal(diagnostic, label="J2-OFF diagnostic")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "kind": DIAGNOSTIC_KIND,
        "release_id": context.release_id,
        "profile_id": context.profile_id,
        "ordinal": ordinal,
        "role": context.action(ordinal)["role"],
        "hardware_action_id": context.action(ordinal)["hardware_action_id"],
        "firmware_binary_sha256": context.binding(ordinal)["firmware_binary_sha256"],
        "firmware_elf_sha256": context.binding(ordinal)["firmware_elf_sha256"],
        "transaction_descriptor_sha256": context.binding(ordinal)[
            "transaction_descriptor_sha256"
        ],
        "operator_temperature_c": _temperature(
            operator_temperature_c, context, ordinal
        ),
        "operator_j2_assertion": "OFF",
        "j2_is_device_measured": False,
        "operator_monitoring_state": contract.OPERATOR_MONITORING_CONFIRMATION,
        "operator_screen_state": SCREEN_INITIAL if ordinal == 1 else SCREEN_RECOVERY,
        "get_requests": 4,
        "post_requests": 0,
        "claim_created": False,
        "device_mutation_performed": False,
        "visible_refreshes": 0,
    }
    observed = {
        key: item
        for key, item in diagnostic.items()
        if key not in {"boot_nonce", "integrity"}
    }
    if observed != expected:
        raise PhysicalOnceError("J2-OFF diagnostic release/action binding differs")
    boot_nonce = diagnostic.get("boot_nonce")
    if not isinstance(boot_nonce, str) or BOOT_NONCE.fullmatch(boot_nonce) is None:
        raise PhysicalOnceError("J2-OFF diagnostic boot nonce is invalid")
    return boot_nonce


def _claim_path(context: ReleaseContext, ordinal: int, registry: Path) -> Path:
    action_id = context.action(ordinal)["hardware_action_id"]
    return registry / f"{context.profile_id}-{ordinal:02d}-{action_id}.json"


def _write_new(path: Path, value: Mapping[str, Any], *, label: str) -> None:
    payload = contract.canonical_json_bytes(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    info = path.parent.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise PhysicalOnceError(f"{label} parent is unsafe")
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise PhysicalOnceError(f"{label} already exists") from error
    except OSError as error:
        raise PhysicalOnceError(f"could not create {label}: {error}") from error


def _require_non_symlink_directory_chain(path: Path, *, create: bool) -> Path:
    directory = Path(os.path.abspath(os.fspath(path)))

    def inspect() -> None:
        for candidate in reversed((directory, *directory.parents)):
            try:
                info = candidate.lstat()
            except FileNotFoundError:
                continue
            except OSError as error:
                raise PhysicalOnceError(
                    f"output directory could not be inspected: {error}"
                ) from error
            if stat.S_ISLNK(info.st_mode):
                raise PhysicalOnceError("output directory chain contains a symlink")
            if not stat.S_ISDIR(info.st_mode):
                raise PhysicalOnceError("output parent chain is not a directory")

    inspect()
    if create:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise PhysicalOnceError(
                f"could not create output directory: {error}"
            ) from error
        inspect()
    return directory


def _reserve_output(
    path: Path, *, label: str, binding: Mapping[str, Any]
) -> OutputReservation:
    target = Path(os.path.abspath(os.fspath(path)))
    parent = _require_non_symlink_directory_chain(target.parent, create=True)
    target = parent / target.name
    try:
        existing = target.lstat()
    except FileNotFoundError:
        pass
    except OSError as error:
        raise PhysicalOnceError(f"could not inspect {label}: {error}") from error
    else:
        if stat.S_ISLNK(existing.st_mode):
            raise PhysicalOnceError(f"{label} must not be a symlink")
        raise PhysicalOnceError(f"{label} already exists")

    reservation = _seal(
        {
            **dict(binding),
            "schema_version": SCHEMA_VERSION,
            "kind": OUTPUT_ATTEMPT_KIND,
            "label": label,
            "state": "PRECLAIM_RESERVED",
            "output_file": str(target),
            "created_before_claim": True,
            "created_before_network": True,
            "network_requests_before_reservation": 0,
            "post_requests_before_reservation": 0,
        }
    )
    payload = contract.canonical_json_bytes(reservation) + b"\n"
    try:
        handle = target.open("x+b")
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        held = os.fstat(handle.fileno())
        output = OutputReservation(
            target,
            handle,
            (held.st_dev, held.st_ino),
            reservation,
            label=label,
        )
        output._assert_identity()  # noqa: SLF001 - constructor postcondition
    except FileExistsError as error:
        raise PhysicalOnceError(f"{label} already exists") from error
    except OSError as error:
        if "handle" in locals():
            handle.close()
        raise PhysicalOnceError(f"could not reserve {label}: {error}") from error
    except Exception:
        if "handle" in locals():
            handle.close()
        raise
    return output


def _best_effort_finalize_failure(
    reservation: OutputReservation,
    error: BaseException,
    *,
    claim_may_be_consumed: bool,
) -> None:
    try:
        reservation.finalize_failure(error, claim_may_be_consumed=claim_may_be_consumed)
    except Exception as sink_error:
        print(
            f"runtime-LUT evidence sink failure while recording {type(error).__name__}: "
            f"{sink_error}",
            file=sys.stderr,
        )


def _create_claim(
    context: ReleaseContext,
    ordinal: int,
    *,
    temperature: str,
    authorization: str,
    diagnostic: Mapping[str, Any],
    registry: Path,
) -> Path:
    path = _claim_path(context, ordinal, registry)
    value = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": CLAIM_KIND,
            "release_id": context.release_id,
            "profile_id": context.profile_id,
            "ordinal": ordinal,
            "role": context.action(ordinal)["role"],
            "hardware_action_id": context.action(ordinal)["hardware_action_id"],
            "operator_temperature_c": temperature,
            "authorization_sha256": contract.sha256(authorization.encode("utf-8")),
            "diagnostic_canonical_sha256": diagnostic["integrity"]["canonical_sha256"],
            "state": "permanently_consumed_do_not_retry",
            "created_before_network": True,
        }
    )
    _write_new(path, value, label="permanent host claim")
    return path


def _require_runtime_claim(context: ReleaseContext, registry: Path) -> None:
    path = _claim_path(context, 1, registry)
    if not path.is_file() or path.is_symlink():
        raise PhysicalOnceError(
            "factory-OTP white action requires the prior runtime action claim"
        )
    value = _read_json(path, label="prior runtime permanent claim")
    _validate_seal(value, label="prior runtime permanent claim")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "release_id": context.release_id,
        "profile_id": context.profile_id,
        "ordinal": 1,
        "role": context.action(1)["role"],
        "hardware_action_id": context.action(1)["hardware_action_id"],
        "state": "permanently_consumed_do_not_retry",
        "created_before_network": True,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise PhysicalOnceError(f"prior runtime claim {key} binding differs")


def _headers(
    context: ReleaseContext,
    ordinal: int,
    boot_nonce: str,
    *,
    intent: str,
    arm_nonce: str | None = None,
) -> dict[str, str]:
    action = context.action(ordinal)
    binding = context.binding(ordinal)
    value = {
        "X-EC5-Build-Tag": str(binding["build_tag"]),
        "X-EC5-Test-Id": str(binding["test_id"]),
        "X-EC5-Campaign-Id": str(binding["campaign_id"]),
        "X-EC5-Action-Id": str(action["hardware_action_id"]),
        "X-EC5-Ordinal": str(ordinal),
        "X-EC5-Descriptor-Id": str(action["transaction_descriptor_sha256"]),
        "X-EC5-Boot-Nonce": boot_nonce,
        "X-EC5-Intent": intent,
    }
    if arm_nonce is not None:
        value["X-EC5-Arm-Nonce"] = arm_nonce
    return value


def _expect_arm(
    value: Mapping[str, Any], context: ReleaseContext, ordinal: int, boot_nonce: str
) -> str:
    _expect_identity(value, context, ordinal, label="ARM response")
    action = context.action(ordinal)
    arm_nonce = value.get("arm_nonce")
    if (
        value.get("accepted") is not True
        or value.get("armed") is not True
        or value.get("ordinal") != ordinal
        or value.get("action_id") != action["hardware_action_id"]
        or value.get("boot_nonce") != boot_nonce
        or not isinstance(arm_nonce, str)
        or ARM_NONCE.fullmatch(arm_nonce) is None
    ):
        raise PhysicalOnceUnknown("ARM response differs; retry is forbidden")
    return arm_nonce


def _expect_execute(
    value: Mapping[str, Any], context: ReleaseContext, ordinal: int
) -> None:
    _expect_identity(value, context, ordinal, label="EXECUTE response")
    if (
        value.get("accepted") is not True
        or value.get("job_id") != ordinal
        or value.get("action_id") != context.action(ordinal)["hardware_action_id"]
        or value.get("execute_consumed") is not True
        or value.get("no_retry") is not True
    ):
        raise PhysicalOnceUnknown("EXECUTE response differs; retry is forbidden")


def _expect_terminal_driver(value: Any, context: ReleaseContext, ordinal: int) -> None:
    if not isinstance(value, Mapping):
        raise PhysicalOnceUnknown("terminal driver evidence is absent")
    atlas_role = "atlas" if ordinal == 1 else "white"
    expected_frame_fnv = atlas.FROZEN_IDENTITIES[atlas_role]["frame"][1]
    expected_cs1_fnv = atlas.FROZEN_IDENTITIES[atlas_role]["cs1"][1]
    expected_cs2_fnv = atlas.FROZEN_IDENTITIES[atlas_role]["cs2"][1]
    exact = {
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "mapping_applied": True,
        "pon_busy_seen": True,
        "drf_busy_seen": True,
        "pof_busy_seen": True,
        "pre_command_idle_failure": False,
        "input_fnv1a": expected_frame_fnv,
        "cs1_dtm_fnv1a": expected_cs1_fnv,
        "cs2_dtm_fnv1a": expected_cs2_fnv,
    }
    for key, expected in exact.items():
        if value.get(key) != expected:
            raise PhysicalOnceUnknown(f"terminal driver {key} evidence differs")
    busy_trace = value.get("busy_trace")
    if not isinstance(busy_trace, Mapping) or busy_trace.get("idle_level") != 1:
        raise PhysicalOnceUnknown("terminal driver BUSY idle evidence differs")
    post_psr = busy_trace.get("post_psr")
    safe_finish = busy_trace.get("safe_finish")
    final_gpio = busy_trace.get("final_gpio")
    if (
        not isinstance(post_psr, Mapping)
        or post_psr.get("pre_command_idle_ok") is not True
        or post_psr.get("wait_exit_level") != 1
    ):
        raise PhysicalOnceUnknown(
            "terminal post-PSR idle evidence differs; a new BUSY assertion is not required"
        )
    if (
        not isinstance(safe_finish, Mapping)
        or safe_finish.get("busy_after_pins_low") != 1
        or safe_finish.get("busy_after_5ms") != 1
    ):
        raise PhysicalOnceUnknown("terminal safe-finish BUSY evidence differs")
    if not isinstance(final_gpio, Mapping) or dict(final_gpio) != {
        "busy": 1,
        "rst": 0,
        "cs": 0,
        "cs2": 0,
        "sck": 0,
        "dc": 0,
        "mosi": 0,
    }:
        raise PhysicalOnceUnknown("terminal final GPIO-low evidence differs")


def _terminal_report(
    value: Mapping[str, Any], context: ReleaseContext, ordinal: int
) -> bool:
    binding = context.binding(ordinal)
    if value.get("kind") != f"{binding['kind_prefix']}-report":
        raise PhysicalOnceUnknown("terminal report kind differs; retry is forbidden")
    terminal = value.get("terminal_state")
    if terminal in {"NOT_EXECUTED", None}:
        return False
    _expect_identity(value, context, ordinal, label="terminal report")
    if (
        value.get("ordinal") != ordinal
        or value.get("action_id") != context.action(ordinal)["hardware_action_id"]
        or value.get("driver_called") is not True
        or value.get("driver_call_count_for_action") != 1
        or value.get("no_retry") is not True
    ):
        raise PhysicalOnceUnknown("terminal report action evidence differs")
    if terminal != "COMPLETE" or value.get("result") is not True:
        raise PhysicalOnceUnknown(
            "device reported a terminal fault; set J2 OFF and do not retry"
        )
    _expect_terminal_driver(value.get("driver"), context, ordinal)
    return True


def run_once(
    context: ReleaseContext,
    ordinal: int,
    *,
    operator_temperature_c: str | float | int,
    operator_j2_state: str,
    operator_monitoring_state: str,
    authorization: str,
    diagnostic: Mapping[str, Any],
    requester: Requester,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    poll_count: int = DEFAULT_POLL_COUNT,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Perform one claimed action with exactly two mutation requests."""

    if operator_j2_state != "ON":
        raise PhysicalOnceError("visible run requires operator J2 assertion ON")
    if operator_monitoring_state != contract.OPERATOR_MONITORING_CONFIRMATION:
        raise PhysicalOnceError("operator safety-monitoring confirmation differs")
    if (
        isinstance(poll_count, bool)
        or not isinstance(poll_count, int)
        or not (1 <= poll_count <= 120)
    ):
        raise PhysicalOnceError("poll count must be an integer in 1..120")
    if not isinstance(poll_interval_seconds, (int, float)) or not (
        0 <= float(poll_interval_seconds) <= 5.0
    ):
        raise PhysicalOnceError("poll interval must be in 0..5 seconds")
    temperature = _temperature(operator_temperature_c, context, ordinal)
    if authorization != required_authorization(
        context, ordinal, temperature, diagnostic
    ):
        raise PhysicalOnceError("exact one-shot authorization token differs")
    # required_authorization() has already deep-validated this exact sealed
    # diagnostic and bound both its canonical digest and boot nonce into V2.
    boot_nonce = str(diagnostic["boot_nonce"])
    registry = Path(claim_registry)
    if ordinal == 2:
        _require_runtime_claim(context, registry)
    claim_path = _claim_path(context, ordinal, registry)
    if claim_path.exists():
        raise PhysicalOnceError("this exact visible action already has a host claim")

    # O_EXCL occurs before even a GET. Any later exception is permanent no-retry.
    claim_path = _create_claim(
        context,
        ordinal,
        temperature=temperature,
        authorization=authorization,
        diagnostic=diagnostic,
        registry=registry,
    )
    binding = context.binding(ordinal)
    base = str(binding["base_route"])
    try:
        _read_preflight(
            context,
            ordinal,
            requester,
            headers=_headers(
                context, ordinal, boot_nonce, intent="READ_ONLY_PREFLIGHT"
            ),
            boot_nonce=boot_nonce,
        )
        arm_headers = _headers(
            context, ordinal, boot_nonce, intent=str(binding["arm_intent"])
        )
        arm = requester("POST", f"{base}/arm", arm_headers)
        if arm.status != 201:
            raise PhysicalOnceUnknown(
                f"ARM returned HTTP {arm.status}; retry is forbidden"
            )
        arm_nonce = _expect_arm(arm.body, context, ordinal, boot_nonce)
        execute_headers = _headers(
            context,
            ordinal,
            boot_nonce,
            intent=str(binding["execute_intent"]),
            arm_nonce=arm_nonce,
        )
        executed = requester("POST", f"{base}/execute", execute_headers)
        if executed.status != 202:
            raise PhysicalOnceUnknown(
                f"EXECUTE returned HTTP {executed.status}; retry is forbidden"
            )
        _expect_execute(executed.body, context, ordinal)
        # A full refresh blocks the single-threaded ESP32 WebServer. This
        # fixed wait reduces needless timed-out connections; it is not a
        # success signal and cannot cause another mutation request.
        sleeper(POST_EXECUTE_SETTLE_SECONDS)
        polls = 0
        poll_read_errors = 0
        for index in range(poll_count):
            polls += 1
            try:
                terminal = _get(
                    requester,
                    f"{base}/report",
                    headers=_headers(
                        context, ordinal, boot_nonce, intent="READ_ONLY_REPORT"
                    ),
                )
            except Exception:
                # The ESP32 WebServer cannot answer while its single loop is
                # inside the blocking panel refresh. A timeout/reset here is
                # an allowed read-only poll miss, never permission to repeat
                # ARM or EXECUTE. The fixed poll bound remains authoritative.
                poll_read_errors += 1
            else:
                if _terminal_report(terminal, context, ordinal):
                    break
            if index + 1 < poll_count:
                sleeper(float(poll_interval_seconds))
        else:
            raise PhysicalOnceUnknown(
                "terminal report polling exhausted; retry is forbidden"
            )
    except PhysicalOnceUnknown:
        raise
    except Exception as error:
        raise PhysicalOnceUnknown(
            "network/device outcome is unknown; claim consumed and retry forbidden; "
            "set J2 OFF before a separately authorized recovery flash"
        ) from error

    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": RESULT_KIND,
            "release_id": context.release_id,
            "profile_id": context.profile_id,
            "ordinal": ordinal,
            "role": context.action(ordinal)["role"],
            "hardware_action_id": context.action(ordinal)["hardware_action_id"],
            "operator_temperature_c": temperature,
            "operator_j2_assertion": "ON",
            "j2_is_device_measured": False,
            "operator_monitoring_state": operator_monitoring_state,
            "boot_nonce": boot_nonce,
            "claim_file": str(claim_path.resolve()),
            "claim_file_sha256": contract.sha256(claim_path.read_bytes()),
            "preflight_get_requests_after_claim": 4,
            "arm_posts": 1,
            "execute_posts": 1,
            "post_execute_settle_seconds": POST_EXECUTE_SETTLE_SECONDS,
            "terminal_report_get_requests": polls,
            "terminal_report_read_errors": poll_read_errors,
            "visible_refreshes": 1,
            "outcome": "success",
            "retry_allowed": False,
            "automatic_chaining_performed": False,
            "automatic_recovery_performed": False,
            "profile_switch_performed": False,
        }
    )


def _http_requester(base_url: str, timeout_s: float) -> Requester:
    try:
        parsed = urlparse.urlsplit(base_url)
        hostname = parsed.hostname
    except ValueError as error:
        raise PhysicalOnceError("device base URL is invalid") from error
    if (
        parsed.scheme != "http"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise PhysicalOnceError("device base URL must be an exact plain-http origin")
    try:
        port = parsed.port
    except ValueError as error:
        raise PhysicalOnceError("device origin port is invalid") from error
    # urlsplit treats an explicitly empty port as None, but it is not an exact
    # origin spelling and would otherwise turn a CLI typo into a post-claim
    # urllib failure.
    if parsed.netloc.endswith(":") or port is not None and not (1 <= port <= 65535):
        raise PhysicalOnceError("device origin port must be in 1..65535")
    if (
        isinstance(timeout_s, bool)
        or not isinstance(timeout_s, Real)
        or not math.isfinite(float(timeout_s))
        or not (0.0 < float(timeout_s) <= 30.0)
    ):
        raise PhysicalOnceError("HTTP timeout must be finite and in (0, 30] seconds")
    timeout = float(timeout_s)
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError as error:
        raise PhysicalOnceError(
            "device origin must use a literal IPv4 address"
        ) from error
    if address.version != 4 or not (
        address.is_private or address.is_loopback or address.is_link_local
    ):
        raise PhysicalOnceError(
            "device origin must use a private, loopback, or link-local IPv4 address"
        )
    root = base_url.rstrip("/")

    class _NoRedirect(urlrequest.HTTPRedirectHandler):
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

    # Never inherit HTTP(S)_PROXY. Supplying our redirect-handler subclass to
    # build_opener suppresses the default redirect handler, so action identity
    # and nonces cannot be forwarded to another origin.
    opener = urlrequest.build_opener(urlrequest.ProxyHandler({}), _NoRedirect())

    def request(method: str, endpoint: str, headers: Mapping[str, str]) -> HttpResponse:
        req = urlrequest.Request(
            root + endpoint,
            # data=None is intentional even for POST. urllib otherwise adds a
            # default form Content-Type, which the firmware correctly rejects
            # as a non-bodyless mutation request.
            data=None,
            headers={"Accept": "application/json", **headers},
            method=method,
        )
        try:
            with opener.open(req, timeout=timeout) as response:  # noqa: S310
                raw = response.read(MAX_JSON_BYTES + 1)
                status = response.status
        except urlerror.HTTPError as error:
            raw = error.read(MAX_JSON_BYTES + 1)
            status = error.code
        except (OSError, urlerror.URLError) as error:
            raise PhysicalOnceError(
                f"HTTP {method} {endpoint} failed: {error}"
            ) from error
        if len(raw) > MAX_JSON_BYTES:
            raise PhysicalOnceError("device JSON response is too large")
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PhysicalOnceError("device response is not UTF-8 JSON") from error
        if not isinstance(decoded, Mapping):
            raise PhysicalOnceError("device response root is not an object")
        return HttpResponse(status, decoded)

    return request


def _read_json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        info = Path(path).lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise PhysicalOnceError(f"{label} must be a non-symlink regular file")
        payload = Path(path).read_bytes()
    except OSError as error:
        raise PhysicalOnceError(f"could not read {label}: {error}") from error
    if len(payload) <= 0 or len(payload) > MAX_JSON_BYTES:
        raise PhysicalOnceError(f"{label} size is invalid")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PhysicalOnceError(f"{label} is not UTF-8 JSON") from error
    if not isinstance(value, Mapping):
        raise PhysicalOnceError(f"{label} root is not an object")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command")
    describe_command = commands.add_parser("describe", allow_abbrev=False)
    describe_command.add_argument("--release", type=Path, required=True)
    authorize = commands.add_parser(
        "authorize",
        allow_abbrev=False,
        help="derive an exact token offline; this is not live authorization",
    )
    authorize.add_argument("--release", type=Path, required=True)
    authorize.add_argument("--profile", choices=contract.PROFILES, required=True)
    authorize.add_argument("--ordinal", type=int, choices=(1, 2), required=True)
    authorize.add_argument("--temperature-c", required=True)
    authorize.add_argument("--diagnostic", type=Path, required=True)
    authorize.add_argument(
        "--claim-registry", type=Path, default=DEFAULT_CLAIM_REGISTRY
    )
    authorize.add_argument("--accept-u1-u7", required=True)
    authorize.add_argument(
        "--confirm-monitors",
        choices=(contract.OPERATOR_MONITORING_CONFIRMATION,),
        required=True,
    )
    diagnose = commands.add_parser("diagnose", allow_abbrev=False)
    diagnose.add_argument("--release", type=Path, required=True)
    diagnose.add_argument("--ordinal", type=int, choices=(1, 2), required=True)
    diagnose.add_argument("--temperature-c", required=True)
    diagnose.add_argument("--screen-state", required=True)
    diagnose.add_argument("--confirm-j2", choices=("OFF",), required=True)
    diagnose.add_argument(
        "--confirm-monitors",
        choices=(contract.OPERATOR_MONITORING_CONFIRMATION,),
        required=True,
    )
    diagnose.add_argument("--base-url", required=True)
    diagnose.add_argument("--timeout-s", type=float, default=5.0)
    diagnose.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run", allow_abbrev=False)
    run.add_argument("--release", type=Path, required=True)
    run.add_argument("--ordinal", type=int, choices=(1, 2), required=True)
    run.add_argument("--temperature-c", required=True)
    run.add_argument("--confirm-j2", choices=("ON",), required=True)
    run.add_argument(
        "--confirm-monitors",
        choices=(contract.OPERATOR_MONITORING_CONFIRMATION,),
        required=True,
    )
    run.add_argument("--authorization", required=True)
    run.add_argument("--diagnostic", type=Path, required=True)
    run.add_argument("--base-url", required=True)
    run.add_argument("--timeout-s", type=float, default=5.0)
    run.add_argument("--claim-registry", type=Path, default=DEFAULT_CLAIM_REGISTRY)
    run.add_argument("--poll-count", type=int, default=DEFAULT_POLL_COUNT)
    run.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
    )
    run.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        context = load_release(args.release)
        if args.command == "describe":
            report = describe(context)
        elif args.command == "authorize":
            diagnostic = _read_json(args.diagnostic, label="J2-OFF diagnostic")
            report = offline_authorization(
                context,
                args.ordinal,
                selected_profile_id=args.profile,
                operator_temperature_c=args.temperature_c,
                empirical_acceptance=args.accept_u1_u7,
                operator_monitoring_state=args.confirm_monitors,
                diagnostic=diagnostic,
                claim_registry=args.claim_registry,
            )
        elif args.command == "diagnose":
            requester = _http_requester(args.base_url, args.timeout_s)
            temperature = _temperature(args.temperature_c, context, args.ordinal)
            action = context.action(args.ordinal)
            reservation = _reserve_output(
                args.output,
                label="J2-OFF diagnostic output",
                binding={
                    "release_id": context.release_id,
                    "profile_id": context.profile_id,
                    "ordinal": args.ordinal,
                    "role": action["role"],
                    "hardware_action_id": action["hardware_action_id"],
                    "operator_temperature_c": temperature,
                    "operator_j2_assertion": args.confirm_j2,
                    "operator_screen_state": args.screen_state,
                    "operator_monitoring_state": args.confirm_monitors,
                },
            )
            try:
                try:
                    report = diagnose_j2_off(
                        context,
                        args.ordinal,
                        operator_temperature_c=temperature,
                        operator_screen_state=args.screen_state,
                        operator_j2_state=args.confirm_j2,
                        operator_monitoring_state=args.confirm_monitors,
                        requester=requester,
                    )
                except BaseException as error:
                    _best_effort_finalize_failure(
                        reservation, error, claim_may_be_consumed=False
                    )
                    raise
                try:
                    reservation.finalize(report)
                except PhysicalOnceError as error:
                    _best_effort_finalize_failure(
                        reservation, error, claim_may_be_consumed=False
                    )
                    raise
            finally:
                reservation.close()
        else:
            diagnostic = _read_json(args.diagnostic, label="J2-OFF diagnostic")
            requester = _http_requester(args.base_url, args.timeout_s)
            temperature = _temperature(args.temperature_c, context, args.ordinal)
            diagnostic_sha256 = _validate_seal(diagnostic, label="J2-OFF diagnostic")
            action = context.action(args.ordinal)
            reservation = _reserve_output(
                args.output,
                label="physical-once result",
                binding={
                    "release_id": context.release_id,
                    "profile_id": context.profile_id,
                    "ordinal": args.ordinal,
                    "role": action["role"],
                    "hardware_action_id": action["hardware_action_id"],
                    "transaction_descriptor_sha256": action[
                        "transaction_descriptor_sha256"
                    ],
                    "operator_temperature_c": temperature,
                    "diagnostic_canonical_sha256": diagnostic_sha256,
                    "boot_nonce": diagnostic.get("boot_nonce"),
                    "authorization_sha256": contract.sha256(
                        args.authorization.encode("utf-8")
                    ),
                    "operator_j2_assertion": args.confirm_j2,
                    "operator_monitoring_state": args.confirm_monitors,
                },
            )
            claim_path = _claim_path(context, args.ordinal, Path(args.claim_registry))
            try:
                try:
                    report = run_once(
                        context,
                        args.ordinal,
                        operator_temperature_c=temperature,
                        operator_j2_state=args.confirm_j2,
                        operator_monitoring_state=args.confirm_monitors,
                        authorization=args.authorization,
                        diagnostic=diagnostic,
                        requester=requester,
                        claim_registry=args.claim_registry,
                        poll_count=args.poll_count,
                        poll_interval_seconds=args.poll_interval_seconds,
                    )
                except BaseException as error:
                    _best_effort_finalize_failure(
                        reservation,
                        error,
                        claim_may_be_consumed=claim_path.is_file(),
                    )
                    raise
                try:
                    reservation.finalize(report)
                except PhysicalOnceError as error:
                    unknown = PhysicalOnceUnknown(
                        "visible action completed but its sealed result evidence "
                        "could not be finalized; claim consumed and retry forbidden"
                    )
                    _best_effort_finalize_failure(
                        reservation, unknown, claim_may_be_consumed=True
                    )
                    raise unknown from error
            finally:
                reservation.close()
    except PhysicalOnceUnknown as error:
        print(f"runtime-LUT physical outcome UNKNOWN: {error}", file=sys.stderr)
        return 3
    except PhysicalOnceError as error:
        print(f"runtime-LUT physical-once error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
