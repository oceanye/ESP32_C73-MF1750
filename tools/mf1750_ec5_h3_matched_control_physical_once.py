#!/usr/bin/env python3
"""Fail-closed one-shot runner for the H3 matched no-R20/R21 control.

``describe`` and diagnostic-bound ``authorize`` are offline.  ``diagnose`` is
four GETs only.  ``run`` permanently claims exactly one action before its
first request, performs one bodyless ARM POST and one bodyless EXECUTE POST,
then polls GET-only terminal evidence.  Control and recovery require separate
flashes, fresh J2-OFF diagnostics, authorizations, claims, and invocations.
There is no retry, automatic chaining/recovery, profile switch, upload, serial
access, or raw payload ingress.
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
from tools import mf1750_ec5_h3_matched_control_contract as contract
from tools import mf1750_ec5_h3_matched_control_release as release


SCHEMA_VERSION: Final = 2
DIAGNOSTIC_KIND: Final = "mf1750-ec5-h3-matched-control-c-first-j2-off-diagnostic-v2"
CLAIM_KIND: Final = "mf1750-ec5-h3-matched-control-c-first-permanent-host-claim-v2"
RESULT_KIND: Final = "mf1750-ec5-h3-matched-control-c-first-physical-once-result-v2"
OFFLINE_AUTHORIZATION_KIND: Final = (
    "mf1750-ec5-h3-matched-control-c-first-offline-authorization-token-v2"
)
OUTPUT_ATTEMPT_KIND: Final = "mf1750-ec5-h3-matched-control-c-first-output-attempt-v2"
DEFAULT_CLAIM_REGISTRY: Final = (
    contract.REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_ec5_h3_matched_control_claims_v2"
)
DEFAULT_POLL_COUNT: Final = 60
DEFAULT_POLL_INTERVAL_SECONDS: Final = 1.0
POST_EXECUTE_SETTLE_SECONDS: Final = 30.0
MAX_JSON_BYTES: Final = 4_000_000
BOOT_NONCE = re.compile(r"^[0-9a-f]{16}$")
ARM_NONCE = re.compile(r"^[0-9a-f]{16}$")
SCREEN_INITIAL: Final = "clean_white_initial_pair_not_treatment_finalized"
SCREEN_RECOVERY: Final = "post_matched_control_unrecovered"


class MatchedControlPhysicalError(RuntimeError):
    """A gate failed before mutation or before a known terminal result."""


class MatchedControlPhysicalUnknown(MatchedControlPhysicalError):
    """The permanent claim may be consumed, so retry is forbidden."""


class HttpResponse(NamedTuple):
    status: int
    body: Mapping[str, Any]


class OutputReservation:
    """An O_EXCL evidence sink held open across one diagnostic/action."""

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
            raise MatchedControlPhysicalError(
                f"{self.label} path identity could not be verified: {error}"
            ) from error
        if (
            stat.S_ISLNK(path_info.st_mode)
            or not stat.S_ISREG(path_info.st_mode)
            or not stat.S_ISREG(held_info.st_mode)
            or (path_info.st_dev, path_info.st_ino) != self.identity
            or (held_info.st_dev, held_info.st_ino) != self.identity
        ):
            raise MatchedControlPhysicalError(f"{self.label} path identity changed")

    def _replace(self, value: Mapping[str, Any]) -> None:
        payload = contract.canonical_json_bytes(value) + b"\n"
        self._assert_identity()
        try:
            self.handle.seek(0)
            self.handle.truncate(0)
            self.handle.write(payload)
            self.handle.flush()
            os.fsync(self.handle.fileno())
        except OSError as error:
            raise MatchedControlPhysicalError(
                f"could not finalize {self.label}: {error}"
            ) from error
        self._assert_identity()
        if os.fstat(self.handle.fileno()).st_size != len(payload):
            raise MatchedControlPhysicalError(f"{self.label} final size differs")
        self.finalized = True

    def finalize(self, value: Mapping[str, Any]) -> None:
        self._replace(value)

    def finalize_failure(
        self, error: BaseException, *, claim_may_be_consumed: bool
    ) -> None:
        self._replace(
            _seal(
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
        )

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
            raise MatchedControlPhysicalError(
                f"release has no unique ordinal {ordinal}"
            )
        return matches[0]

    def binding(self, ordinal: int) -> Mapping[str, Any]:
        matches = [
            item
            for item in self.root["action_artifact_bindings"]
            if item["ordinal"] == ordinal
        ]
        if len(matches) != 1:
            raise MatchedControlPhysicalError(
                f"release has no unique binding {ordinal}"
            )
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
        raise MatchedControlPhysicalError(f"{label} is not sealed")
    expected = _seal({key: item for key, item in value.items() if key != "integrity"})[
        "integrity"
    ]
    if dict(integrity) != expected:
        raise MatchedControlPhysicalError(f"{label} integrity mismatch")
    return str(integrity["canonical_sha256"])


def context_from_root(root: Mapping[str, Any]) -> ReleaseContext:
    try:
        release.validate_release(root)
    except release.MatchedControlReleaseError as error:
        raise MatchedControlPhysicalError(
            f"release validation failed: {error}"
        ) from error
    return ReleaseContext(root=dict(root))


def load_release(path: Path) -> ReleaseContext:
    try:
        root = release.load_release(path)
    except release.MatchedControlReleaseError as error:
        raise MatchedControlPhysicalError(
            f"release validation failed: {error}"
        ) from error
    return ReleaseContext(root=root, release_file=Path(path).resolve())


def _require_release_execution_gate(context: ReleaseContext) -> None:
    prerequisites = context.root.get("live_authorization_prerequisites")
    trace_binding = context.root.get("compiled_treatment_control_trace_binding")
    treatment = context.root.get("pinned_treatment_release")
    if (
        context.root.get("typed_treatment_control_trace_materialized") is not True
        or context.root.get("execution_eligible_after_all_runner_gates") is not True
        or not isinstance(prerequisites, Mapping)
        or prerequisites.get("typed_treatment_control_trace_gate_required") is not True
        or prerequisites.get("typed_treatment_control_trace_gate_materialized")
        is not True
        or not isinstance(trace_binding, Mapping)
        or not isinstance(treatment, Mapping)
        or treatment.get("release_id") != contract.PINNED_TREATMENT_RELEASE_ID
        or treatment.get("sha256") != contract.PINNED_TREATMENT_RELEASE_FILE_SHA256
        or trace_binding.get("strip_exact_four_upload_spans_equals_control") is not True
        or trace_binding.get("transitive_build_manifest_bound") is not True
        or trace_binding.get("T_equals_C_classification")
        != "NO_DETECTABLE_INCREMENTAL_EFFECT"
    ):
        raise MatchedControlPhysicalError(
            "release lacks the deep-replayed typed treatment/control trace gate"
        )


def _temperature(
    value: str | float | int, context: ReleaseContext, ordinal: int
) -> str:
    try:
        decimal = Decimal(str(value))
    except InvalidOperation as error:
        raise MatchedControlPhysicalError(
            "operator temperature is not numeric"
        ) from error
    if not decimal.is_finite() or decimal != decimal.quantize(Decimal("0.1")):
        raise MatchedControlPhysicalError(
            "operator temperature must be a finite 0.1 C value"
        )
    action = context.action(ordinal)
    policy = action["temperature_policy"]
    if ordinal == 1:
        minimum, maximum = policy["allowed_c"]
        if decimal < Decimal(str(minimum)) or decimal > Decimal(str(maximum)):
            raise MatchedControlPhysicalError(
                "matched control temperature is outside the exact 25.0 C "
                "experimental guard; this is not a vendor temperature qualification"
            )
    else:
        minimum, maximum = policy["allowed_record_range_c"]
        if decimal < Decimal(str(minimum)) or decimal > Decimal(str(maximum)):
            raise MatchedControlPhysicalError(
                "OTP recovery temperature is outside the supervised record guard"
            )
    return f"{decimal:.1f}"


def required_authorization(
    context: ReleaseContext,
    ordinal: int,
    operator_temperature_c: str | float | int,
    diagnostic: Mapping[str, Any],
) -> str:
    _require_release_execution_gate(context)
    action = context.action(ordinal)
    temperature = _temperature(operator_temperature_c, context, ordinal)
    boot_nonce = validate_diagnostic(
        context,
        ordinal,
        diagnostic,
        operator_temperature_c=temperature,
    )
    diagnostic_sha = str(diagnostic["integrity"]["canonical_sha256"])
    treatment = context.root["pinned_treatment_release"]
    trace = context.root["compiled_treatment_control_trace_binding"]
    risks = context.root["profile_contract"]["risk_acceptance"]
    monitor_sha = contract.sha256(
        contract.OPERATOR_MONITORING_CONFIRMATION.encode("ascii")
    )
    initial_sha = contract.sha256(contract.INITIAL_PRECONDITION_PHRASE.encode("ascii"))
    role = "NO_R20_R21_CONTROL" if ordinal == 1 else "CONTROL_OTP_WHITE"
    slug = temperature.replace("-", "M").replace(".", "P")
    stage_gate = (
        f"__INITIAL_PRECONDITION_{initial_sha.upper()}"
        if ordinal == 1
        else "__CONTROL_CLAIM_REQUIRED_FOR_CONTAINMENT_RECOVERY"
    )
    return (
        f"AUTHORIZE_ONE_VISIBLE_EC5_H3_MATCHED_{role}_ORDINAL_{ordinal:02d}"
        f"__TEMP_C_{slug}__RELEASE_{context.release_id.upper()}"
        f"__ACTION_{action['hardware_action_id'].upper()}"
        f"__DESCRIPTOR_{action['transaction_descriptor_sha256'].upper()}"
        f"__TREATMENT_RELEASE_{treatment['release_id'].upper()}"
        f"__TRACE_AUDIT_{trace['audit_id'].upper()}"
        f"__DIAGNOSTIC_{diagnostic_sha.upper()}"
        f"__BOOT_NONCE_{boot_nonce.upper()}"
        f"__ACCEPT_C1_C8_{risks['canonical_sha256'].upper()}"
        f"__MONITORS_{monitor_sha.upper()}"
        f"{stage_gate}"
        "__NO_RETRY_NO_RECOVERY_NO_AUTOCHAIN_NO_PROFILE_SWITCH"
    )


def offline_authorization(
    context: ReleaseContext,
    ordinal: int,
    *,
    selected_profile_id: str,
    operator_temperature_c: str | float | int,
    control_acceptance: str,
    initial_precondition: str | None,
    operator_monitoring_state: str,
    diagnostic: Mapping[str, Any],
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    """Derive a sealed token offline without creating a claim or request."""

    if selected_profile_id != context.profile_id:
        raise MatchedControlPhysicalError("selected profile differs from release")
    if control_acceptance != contract.CONTROL_ACCEPTANCE_PHRASE:
        raise MatchedControlPhysicalError("exact C1-C8 acceptance is absent")
    if ordinal == 1 and initial_precondition != contract.INITIAL_PRECONDITION_PHRASE:
        raise MatchedControlPhysicalError(
            "exact initial C-first precondition is absent"
        )
    if operator_monitoring_state != contract.OPERATOR_MONITORING_CONFIRMATION:
        raise MatchedControlPhysicalError("monitoring confirmation differs")
    if ordinal == 2:
        _require_control_claim(context, Path(claim_registry))
    temperature = _temperature(operator_temperature_c, context, ordinal)
    token = required_authorization(context, ordinal, temperature, diagnostic)
    action = context.action(ordinal)
    treatment = context.root["pinned_treatment_release"]
    trace = context.root["compiled_treatment_control_trace_binding"]
    risks = context.root["profile_contract"]["risk_acceptance"]
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": OFFLINE_AUTHORIZATION_KIND,
            "profile_id": context.profile_id,
            "release_id": context.release_id,
            "ordinal": ordinal,
            "role": action["role"],
            "hardware_action_id": action["hardware_action_id"],
            "transaction_descriptor_sha256": action["transaction_descriptor_sha256"],
            "treatment_release_id": treatment["release_id"],
            "compiled_trace_audit_id": trace["audit_id"],
            "operator_temperature_c": temperature,
            "diagnostic_canonical_sha256": diagnostic["integrity"]["canonical_sha256"],
            "boot_nonce": diagnostic["boot_nonce"],
            "c1_c8": risks["risks"],
            "c1_c8_exact_phrase": control_acceptance,
            "initial_precondition_exact_phrase": (
                initial_precondition if ordinal == 1 else None
            ),
            "initial_clean_white_is_treatment_finalized_evidence": False,
            "c1_c8_acceptance_sha256": risks["canonical_sha256"],
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
            "fresh_j2_off_diagnostic_and_run_gates_still_required": True,
        }
    )


def describe(context: ReleaseContext) -> dict[str, Any]:
    treatment = context.root["pinned_treatment_release"]
    return {
        "profile_id": context.profile_id,
        "release_id": context.release_id,
        "pinned_treatment_release_id": treatment["release_id"],
        "control_temperature_allowed_c": context.root["c_first_temperature_policy"][
            "control_temperature_allowed_c"
        ],
        "control_temperature_establishes_later_treatment_temperature": True,
        "initial_clean_white_is_treatment_finalized_evidence": False,
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
                "separate_flash_diagnostic_authorization_required": True,
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
    action = context.action(ordinal)
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
            context.profile_id, action["role"]
        ),
        "running_app_elf_sha256": binding["firmware_elf_sha256"],
    }


def _expect_identity(
    value: Mapping[str, Any], context: ReleaseContext, ordinal: int, *, label: str
) -> None:
    for key, expected in _identity_expected(context, ordinal).items():
        if value.get(key) != expected:
            raise MatchedControlPhysicalError(f"{label} {key} identity differs")


def _get(
    requester: Requester,
    endpoint: str,
    *,
    headers: Mapping[str, str] | None = None,
) -> Mapping[str, Any]:
    response = requester("GET", endpoint, headers or {})
    if response.status != 200:
        raise MatchedControlPhysicalError(
            f"GET {endpoint} returned HTTP {response.status}"
        )
    return response.body


def _expect_version(
    value: Mapping[str, Any], context: ReleaseContext, ordinal: int
) -> None:
    action = context.action(ordinal)
    binding = context.binding(ordinal)
    if value.get("schema_version") != 1 or value.get("kind") != (
        f"{binding['kind_prefix']}-version"
    ):
        raise MatchedControlPhysicalError("device version schema/kind differs")
    _expect_identity(value, context, ordinal, label="version")
    profile = value.get("profile")
    if not isinstance(profile, Mapping):
        raise MatchedControlPhysicalError("device version profile is absent")
    policy = action["temperature_policy"]
    interval = policy["allowed_c"] if ordinal == 1 else policy["allowed_record_range_c"]
    manifest_temperature_tokens = (
        context.root["profile_contract"]["vendor_filename_numeric_tokens"]
        if ordinal == 1
        else interval
    )
    if (
        profile.get("profile_id") != context.profile_id
        or profile.get("compiled_profile_count") != 1
        or profile.get("auto_selected") is not False
        # The unchanged V2 firmware field names preserve opaque filename
        # tokens for the control image; they are not the live temperature
        # interval.  Recovery continues to report its 0..37 record guard.
        or profile.get("apparent_temperature_min_c")
        != int(manifest_temperature_tokens[0])
        or profile.get("apparent_temperature_max_c")
        != int(manifest_temperature_tokens[1])
        or value.get("action_count") != 1
        or value.get("startup_refresh") is not False
        or value.get("raw_ingress") is not False
        or value.get("retry") is not False
        or value.get("automatic_chaining") is not False
        or value.get("automatic_recovery") is not False
        or value.get("profile_switch") is not False
    ):
        raise MatchedControlPhysicalError("device version safety/profile differs")
    if ordinal == 1:
        if (
            policy.get("kind") != "initial_control_at_experimental_fixed_25_guard"
            or policy.get("allowed_c") != [25.0, 25.0]
            or policy.get("vendor_filename_band_claim") is not False
            or policy.get("temperature_compatibility_qualified") is not False
            or context.root["profile_contract"].get(
                "temperature_filename_semantics_proven"
            )
            is not False
            or context.root["profile_contract"].get(
                "temperature_compatibility_qualified"
            )
            is not False
        ):
            raise MatchedControlPhysicalError(
                "experimental fixed-temperature guard differs"
            )
        electrical = contract.profile_row()["requested_electrical_metadata"]
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
            observed != electrical
            or profile.get("electrical_values_source") != "matched_wf20_25_constants"
            or profile.get("r20_command_writes") != 0
            or profile.get("r21_command_writes") != 0
            or profile.get("r20_payload_bytes") != 0
            or profile.get("r21_payload_bytes") != 0
            or profile.get("control_design") != contract.CONTROL_DESIGN
            or profile.get("strict_payload_only_control") is not False
            or profile.get("time_matched_control") is not False
            or profile.get("dummy_clocks_inserted") is not False
            or profile.get("empty_r20_or_r21_commands_inserted") is not False
        ):
            raise MatchedControlPhysicalError(
                "device matched-control electrical/command surface differs"
            )
    elif (
        profile.get("temperature_policy")
        != "factory_otp_existing_observed_ceiling_not_vendor_band"
        or profile.get("temperature_limit_is_safety_qualification") is not False
    ):
        raise MatchedControlPhysicalError("recovery temperature policy differs")


def _expect_manifest(
    value: Mapping[str, Any], context: ReleaseContext, ordinal: int
) -> None:
    binding = context.binding(ordinal)
    action = context.action(ordinal)
    if value.get("schema_version") != 1 or value.get("kind") != (
        f"{binding['kind_prefix']}-manifest"
    ):
        raise MatchedControlPhysicalError("device manifest schema/kind differs")
    _expect_identity(value, context, ordinal, label="manifest")
    expected_action = {
        "ordinal": ordinal,
        "role": action["role"],
        "descriptor_id": action["transaction_descriptor_sha256"],
        "action_id": action["hardware_action_id"],
        "frame_sha256": action["payload_identity"]["frame_sha256"],
        "cs1_dtm_sha256": action["payload_identity"]["cs1_dtm_sha256"],
        "cs2_dtm_sha256": action["payload_identity"]["cs2_dtm_sha256"],
    }
    if value.get("actions") != [expected_action]:
        raise MatchedControlPhysicalError("device manifest action differs")
    false_flags = (
        "startup_refresh",
        "raw_frame_ingress",
        "raw_lut_ingress",
        "electrical_parameter_ingress",
        "timing_parameter_ingress",
        "retry",
        "automatic_chaining",
        "automatic_recovery",
        "profile_switch",
        "vcom_write",
        "vcom_sweep",
    )
    if any(value.get(key) is not False for key in false_flags):
        raise MatchedControlPhysicalError("device manifest safety flags differ")
    if (
        value.get("action_count") != 1
        or value.get("one_driver_call_per_action") is not True
    ):
        raise MatchedControlPhysicalError("device manifest action count differs")
    risks = value.get("unproven_risks")
    if (
        not isinstance(risks, list)
        or [item.get("id") for item in risks] != [f"C{index}" for index in range(1, 9)]
        or any(item.get("status") != "unproven" for item in risks)
    ):
        raise MatchedControlPhysicalError("device manifest C1-C8 surface differs")
    if ordinal == 1 and (
        value.get("r20_command_writes") != 0
        or value.get("r21_command_writes") != 0
        or value.get("r20_payload_bytes") != 0
        or value.get("r21_payload_bytes") != 0
        or value.get("control_design") != contract.CONTROL_DESIGN
        or value.get("strict_payload_only_control") is not False
        or value.get("time_matched_control") is not False
        or value.get("dummy_clocks_inserted") is not False
        or value.get("empty_r20_or_r21_commands_inserted") is not False
        or value.get("per_controller_removed_spi_bytes_and_edges") != 1505
        or value.get("per_controller_removed_cooperative_yields") != 5
    ):
        raise MatchedControlPhysicalError("device manifest R20/R21 omission differs")


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
        raise MatchedControlPhysicalError("device status schema/kind differs")
    _expect_identity(value, context, ordinal, label="status")
    observed_nonce = value.get("boot_nonce")
    if (
        not isinstance(observed_nonce, str)
        or BOOT_NONCE.fullmatch(observed_nonce) is None
    ):
        raise MatchedControlPhysicalError("device boot nonce is invalid")
    if boot_nonce is not None and observed_nonce != boot_nonce:
        raise MatchedControlPhysicalError("device rebooted after the J2-OFF diagnostic")
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
        or any(value.get(pin) != 0 for pin in ("rst", "cs", "cs2", "sck", "dc", "mosi"))
        or value.get("busy") not in (0, 1)
    ):
        raise MatchedControlPhysicalError("device status is not virgin ready")
    return observed_nonce


def _expect_preflight_report(
    value: Mapping[str, Any], context: ReleaseContext, ordinal: int
) -> None:
    binding = context.binding(ordinal)
    if value.get("schema_version") != 1 or value.get("kind") != (
        f"{binding['kind_prefix']}-report"
    ):
        raise MatchedControlPhysicalError("device report schema/kind differs")
    _expect_identity(value, context, ordinal, label="preflight report")
    if (
        value.get("terminal_state") != "NOT_EXECUTED"
        or value.get("result") is not False
        or value.get("driver_called") is not False
        or value.get("driver_call_count_for_action") != 0
        or value.get("no_retry") is not True
    ):
        raise MatchedControlPhysicalError("device preflight report is not virgin")


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
    nonce = _expect_status(payloads["status"], context, ordinal, boot_nonce=boot_nonce)
    _expect_preflight_report(payloads["report"], context, ordinal)
    return nonce, payloads


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
    """Perform exactly four read-only GETs after operator J2-OFF assertion."""

    _require_release_execution_gate(context)
    temperature = _temperature(operator_temperature_c, context, ordinal)
    expected_screen = SCREEN_INITIAL if ordinal == 1 else SCREEN_RECOVERY
    if operator_j2_state != "OFF":
        raise MatchedControlPhysicalError("diagnostic requires J2 OFF")
    if operator_monitoring_state != contract.OPERATOR_MONITORING_CONFIRMATION:
        raise MatchedControlPhysicalError("monitoring confirmation differs")
    if operator_screen_state != expected_screen:
        raise MatchedControlPhysicalError(
            f"ordinal {ordinal} requires screen state {expected_screen!r}"
        )
    boot_nonce, _ = _read_preflight(context, ordinal, requester)
    action = context.action(ordinal)
    treatment = context.root["pinned_treatment_release"]
    trace = context.root["compiled_treatment_control_trace_binding"]
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": DIAGNOSTIC_KIND,
            "release_id": context.release_id,
            "profile_id": context.profile_id,
            "ordinal": ordinal,
            "role": action["role"],
            "hardware_action_id": action["hardware_action_id"],
            "firmware_binary_sha256": context.binding(ordinal)[
                "firmware_binary_sha256"
            ],
            "firmware_elf_sha256": context.binding(ordinal)["firmware_elf_sha256"],
            "transaction_descriptor_sha256": context.binding(ordinal)[
                "transaction_descriptor_sha256"
            ],
            "treatment_release_id": treatment["release_id"],
            "compiled_trace_audit_id": trace["audit_id"],
            "boot_nonce": boot_nonce,
            "operator_temperature_c": temperature,
            "operator_j2_assertion": "OFF",
            "j2_is_device_measured": False,
            "operator_monitoring_state": operator_monitoring_state,
            "operator_screen_state": operator_screen_state,
            "initial_clean_white_is_treatment_finalized_evidence": False,
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
    action = context.action(ordinal)
    expected = {
        "schema_version": SCHEMA_VERSION,
        "kind": DIAGNOSTIC_KIND,
        "release_id": context.release_id,
        "profile_id": context.profile_id,
        "ordinal": ordinal,
        "role": action["role"],
        "hardware_action_id": action["hardware_action_id"],
        "firmware_binary_sha256": context.binding(ordinal)["firmware_binary_sha256"],
        "firmware_elf_sha256": context.binding(ordinal)["firmware_elf_sha256"],
        "transaction_descriptor_sha256": context.binding(ordinal)[
            "transaction_descriptor_sha256"
        ],
        "treatment_release_id": context.root["pinned_treatment_release"]["release_id"],
        "compiled_trace_audit_id": context.root[
            "compiled_treatment_control_trace_binding"
        ]["audit_id"],
        "operator_temperature_c": _temperature(
            operator_temperature_c, context, ordinal
        ),
        "operator_j2_assertion": "OFF",
        "j2_is_device_measured": False,
        "operator_monitoring_state": contract.OPERATOR_MONITORING_CONFIRMATION,
        "operator_screen_state": SCREEN_INITIAL if ordinal == 1 else SCREEN_RECOVERY,
        "initial_clean_white_is_treatment_finalized_evidence": False,
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
        raise MatchedControlPhysicalError(
            "J2-OFF diagnostic release/action binding differs"
        )
    boot_nonce = diagnostic.get("boot_nonce")
    if not isinstance(boot_nonce, str) or BOOT_NONCE.fullmatch(boot_nonce) is None:
        raise MatchedControlPhysicalError("diagnostic boot nonce is invalid")
    return boot_nonce


def _claim_path(context: ReleaseContext, ordinal: int, registry: Path) -> Path:
    action_id = context.action(ordinal)["hardware_action_id"]
    return registry / (
        f"matched-c-first-{context.profile_id}-{ordinal:02d}-{action_id}.json"
    )


def _require_non_symlink_directory_chain(path: Path, *, create: bool) -> Path:
    directory = Path(os.path.abspath(os.fspath(path)))

    def inspect() -> None:
        for candidate in reversed((directory, *directory.parents)):
            try:
                info = candidate.lstat()
            except FileNotFoundError:
                continue
            except OSError as error:
                raise MatchedControlPhysicalError(
                    f"output directory could not be inspected: {error}"
                ) from error
            if stat.S_ISLNK(info.st_mode):
                raise MatchedControlPhysicalError(
                    "output directory chain contains a symlink"
                )
            if not stat.S_ISDIR(info.st_mode):
                raise MatchedControlPhysicalError(
                    "output parent chain is not a directory"
                )

    inspect()
    if create:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise MatchedControlPhysicalError(
                f"could not create output directory: {error}"
            ) from error
        inspect()
    return directory


def _write_new(path: Path, value: Mapping[str, Any], *, label: str) -> None:
    payload = contract.canonical_json_bytes(value) + b"\n"
    target = Path(os.path.abspath(os.fspath(path)))
    parent = _require_non_symlink_directory_chain(target.parent, create=True)
    target = parent / target.name
    try:
        with target.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise MatchedControlPhysicalError(f"{label} already exists") from error
    except OSError as error:
        raise MatchedControlPhysicalError(
            f"could not create {label}: {error}"
        ) from error


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
        raise MatchedControlPhysicalError(
            f"could not inspect {label}: {error}"
        ) from error
    else:
        if stat.S_ISLNK(existing.st_mode):
            raise MatchedControlPhysicalError(f"{label} must not be a symlink")
        raise MatchedControlPhysicalError(f"{label} already exists")
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
        raise MatchedControlPhysicalError(f"{label} already exists") from error
    except OSError as error:
        if "handle" in locals():
            handle.close()
        raise MatchedControlPhysicalError(
            f"could not reserve {label}: {error}"
        ) from error
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
            "matched-control evidence sink failure while recording "
            f"{type(error).__name__}: {sink_error}",
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
    treatment = context.root["pinned_treatment_release"]
    trace = context.root["compiled_treatment_control_trace_binding"]
    value = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": CLAIM_KIND,
            "release_id": context.release_id,
            "profile_id": context.profile_id,
            "ordinal": ordinal,
            "role": context.action(ordinal)["role"],
            "hardware_action_id": context.action(ordinal)["hardware_action_id"],
            "treatment_release_id": treatment["release_id"],
            "compiled_trace_audit_id": trace["audit_id"],
            "operator_temperature_c": temperature,
            "authorization_sha256": contract.sha256(authorization.encode("utf-8")),
            "diagnostic_canonical_sha256": diagnostic["integrity"]["canonical_sha256"],
            "state": "permanently_consumed_do_not_retry",
            "created_before_network": True,
        }
    )
    _write_new(path, value, label="matched-control permanent host claim")
    return path


def _read_json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        before = Path(path).lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise MatchedControlPhysicalError(
                f"{label} must be a non-symlink regular file"
            )
        payload = Path(path).read_bytes()
        after = Path(path).lstat()
    except OSError as error:
        raise MatchedControlPhysicalError(f"could not read {label}: {error}") from error
    if (
        len(payload) <= 0
        or len(payload) > MAX_JSON_BYTES
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise MatchedControlPhysicalError(f"{label} size/identity is invalid")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MatchedControlPhysicalError(f"{label} is not UTF-8 JSON") from error
    if not isinstance(value, Mapping):
        raise MatchedControlPhysicalError(f"{label} root is not an object")
    return value


def _require_control_claim(context: ReleaseContext, registry: Path) -> None:
    path = _claim_path(context, 1, registry)
    if not path.is_file() or path.is_symlink():
        raise MatchedControlPhysicalError(
            "OTP-white recovery requires the prior matched-control claim"
        )
    value = _read_json(path, label="prior matched-control claim")
    _validate_seal(value, label="prior matched-control claim")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "release_id": context.release_id,
        "profile_id": context.profile_id,
        "ordinal": 1,
        "role": context.action(1)["role"],
        "hardware_action_id": context.action(1)["hardware_action_id"],
        "treatment_release_id": context.root["pinned_treatment_release"]["release_id"],
        "compiled_trace_audit_id": context.root[
            "compiled_treatment_control_trace_binding"
        ]["audit_id"],
        "state": "permanently_consumed_do_not_retry",
        "created_before_network": True,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise MatchedControlPhysicalError(f"prior control claim {key} differs")


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
    headers = {
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
        headers["X-EC5-Arm-Nonce"] = arm_nonce
    return headers


def _expect_arm(
    value: Mapping[str, Any], context: ReleaseContext, ordinal: int, boot_nonce: str
) -> str:
    _expect_identity(value, context, ordinal, label="ARM response")
    arm_nonce = value.get("arm_nonce")
    if (
        value.get("accepted") is not True
        or value.get("armed") is not True
        or value.get("ordinal") != ordinal
        or value.get("action_id") != context.action(ordinal)["hardware_action_id"]
        or value.get("boot_nonce") != boot_nonce
        or not isinstance(arm_nonce, str)
        or ARM_NONCE.fullmatch(arm_nonce) is None
    ):
        raise MatchedControlPhysicalUnknown("ARM response differs; retry is forbidden")
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
        raise MatchedControlPhysicalUnknown(
            "EXECUTE response differs; retry is forbidden"
        )


def _expect_terminal_driver(value: Any, context: ReleaseContext, ordinal: int) -> None:
    if not isinstance(value, Mapping):
        raise MatchedControlPhysicalUnknown("terminal driver evidence is absent")
    atlas_role = "atlas" if ordinal == 1 else "white"
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
        "input_fnv1a": atlas.FROZEN_IDENTITIES[atlas_role]["frame"][1],
        "cs1_dtm_fnv1a": atlas.FROZEN_IDENTITIES[atlas_role]["cs1"][1],
        "cs2_dtm_fnv1a": atlas.FROZEN_IDENTITIES[atlas_role]["cs2"][1],
    }
    if ordinal == 1:
        exact.update(
            {
                "matched_no_r20_r21_control": True,
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
            }
        )
    else:
        exact.update(
            {
                "factory_otp_white": True,
                "matched_no_r20_r21_control": False,
            }
        )
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise MatchedControlPhysicalUnknown(
                f"terminal driver {key} evidence differs"
            )
    trace = value.get("busy_trace")
    if not isinstance(trace, Mapping) or trace.get("idle_level") != 1:
        raise MatchedControlPhysicalUnknown("terminal BUSY idle evidence differs")
    post_psr = trace.get("post_psr")
    safe_finish = trace.get("safe_finish")
    final_gpio = trace.get("final_gpio")
    if (
        not isinstance(post_psr, Mapping)
        or post_psr.get("pre_command_idle_ok") is not True
        or post_psr.get("wait_exit_level") != 1
    ):
        raise MatchedControlPhysicalUnknown("terminal post-PSR evidence differs")
    if (
        not isinstance(safe_finish, Mapping)
        or safe_finish.get("busy_after_pins_low") != 1
        or safe_finish.get("busy_after_5ms") != 1
    ):
        raise MatchedControlPhysicalUnknown("terminal safe-finish evidence differs")
    if not isinstance(final_gpio, Mapping) or dict(final_gpio) != {
        "busy": 1,
        "rst": 0,
        "cs": 0,
        "cs2": 0,
        "sck": 0,
        "dc": 0,
        "mosi": 0,
    }:
        raise MatchedControlPhysicalUnknown("terminal final GPIO evidence differs")


def _terminal_report(
    value: Mapping[str, Any], context: ReleaseContext, ordinal: int
) -> bool:
    binding = context.binding(ordinal)
    if value.get("kind") != f"{binding['kind_prefix']}-report":
        raise MatchedControlPhysicalUnknown("terminal report kind differs")
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
        raise MatchedControlPhysicalUnknown("terminal action evidence differs")
    if terminal != "COMPLETE" or value.get("result") is not True:
        raise MatchedControlPhysicalUnknown(
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

    _require_release_execution_gate(context)
    if operator_j2_state != "ON":
        raise MatchedControlPhysicalError("visible run requires J2 ON")
    if operator_monitoring_state != contract.OPERATOR_MONITORING_CONFIRMATION:
        raise MatchedControlPhysicalError("monitoring confirmation differs")
    silent_window = context.root.get("post_execute_silent_window")
    if (
        not isinstance(silent_window, Mapping)
        or silent_window.get("seconds") != POST_EXECUTE_SETTLE_SECONDS
        or silent_window.get("same_as_empirical_h3_runner") is not True
        or silent_window.get("no_request_during_window") is not True
        or silent_window.get("only_get_polling_allowed_after_window") is not True
    ):
        raise MatchedControlPhysicalError("fixed post-execute silent window differs")
    if (
        isinstance(poll_count, bool)
        or not isinstance(poll_count, int)
        or not (1 <= poll_count <= 120)
    ):
        raise MatchedControlPhysicalError("poll count must be in 1..120")
    if (
        isinstance(poll_interval_seconds, bool)
        or not isinstance(poll_interval_seconds, Real)
        or not math.isfinite(float(poll_interval_seconds))
        or not (0 <= float(poll_interval_seconds) <= 5.0)
    ):
        raise MatchedControlPhysicalError("poll interval must be in 0..5 seconds")
    temperature = _temperature(operator_temperature_c, context, ordinal)
    if authorization != required_authorization(
        context, ordinal, temperature, diagnostic
    ):
        raise MatchedControlPhysicalError("one-shot authorization token differs")
    boot_nonce = str(diagnostic["boot_nonce"])
    registry = Path(claim_registry)
    if ordinal == 2:
        _require_control_claim(context, registry)
    claim_path = _claim_path(context, ordinal, registry)
    if claim_path.exists():
        raise MatchedControlPhysicalError("this exact action already has a claim")
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
        arm = requester(
            "POST",
            f"{base}/arm",
            _headers(
                context,
                ordinal,
                boot_nonce,
                intent=str(binding["arm_intent"]),
            ),
        )
        if arm.status != 201:
            raise MatchedControlPhysicalUnknown(
                f"ARM returned HTTP {arm.status}; retry is forbidden"
            )
        arm_nonce = _expect_arm(arm.body, context, ordinal, boot_nonce)
        executed = requester(
            "POST",
            f"{base}/execute",
            _headers(
                context,
                ordinal,
                boot_nonce,
                intent=str(binding["execute_intent"]),
                arm_nonce=arm_nonce,
            ),
        )
        if executed.status != 202:
            raise MatchedControlPhysicalUnknown(
                f"EXECUTE returned HTTP {executed.status}; retry is forbidden"
            )
        _expect_execute(executed.body, context, ordinal)
        sleeper(POST_EXECUTE_SETTLE_SECONDS)
        polls = 0
        poll_errors = 0
        for index in range(poll_count):
            polls += 1
            try:
                terminal = _get(
                    requester,
                    f"{base}/report",
                    headers=_headers(
                        context,
                        ordinal,
                        boot_nonce,
                        intent="READ_ONLY_REPORT",
                    ),
                )
            except Exception:
                poll_errors += 1
            else:
                if _terminal_report(terminal, context, ordinal):
                    break
            if index + 1 < poll_count:
                sleeper(float(poll_interval_seconds))
        else:
            raise MatchedControlPhysicalUnknown(
                "terminal polling exhausted; retry is forbidden"
            )
    except MatchedControlPhysicalUnknown:
        raise
    except Exception as error:
        raise MatchedControlPhysicalUnknown(
            "network/device outcome unknown; claim consumed; set J2 OFF and do not retry"
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
            "treatment_release_id": context.root["pinned_treatment_release"][
                "release_id"
            ],
            "compiled_trace_audit_id": context.root[
                "compiled_treatment_control_trace_binding"
            ]["audit_id"],
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
            "terminal_report_read_errors": poll_errors,
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
        raise MatchedControlPhysicalError("device base URL is invalid") from error
    if (
        parsed.scheme != "http"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise MatchedControlPhysicalError(
            "device base URL must be an exact plain-http origin"
        )
    try:
        port = parsed.port
    except ValueError as error:
        raise MatchedControlPhysicalError("device origin port is invalid") from error
    if parsed.netloc.endswith(":") or port is not None and not (1 <= port <= 65535):
        raise MatchedControlPhysicalError("device origin port is invalid")
    if (
        isinstance(timeout_s, bool)
        or not isinstance(timeout_s, Real)
        or not math.isfinite(float(timeout_s))
        or not (0.0 < float(timeout_s) <= 30.0)
    ):
        raise MatchedControlPhysicalError("HTTP timeout must be in (0,30]")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError as error:
        raise MatchedControlPhysicalError(
            "device origin must use a literal IPv4 address"
        ) from error
    if address.version != 4 or not (
        address.is_private or address.is_loopback or address.is_link_local
    ):
        raise MatchedControlPhysicalError("device origin must be local/private IPv4")
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

    opener = urlrequest.build_opener(urlrequest.ProxyHandler({}), _NoRedirect())

    def request(method: str, endpoint: str, headers: Mapping[str, str]) -> HttpResponse:
        req = urlrequest.Request(
            root + endpoint,
            data=None,
            headers={"Accept": "application/json", **headers},
            method=method,
        )
        try:
            with opener.open(req, timeout=float(timeout_s)) as response:  # noqa: S310
                raw = response.read(MAX_JSON_BYTES + 1)
                status = response.status
        except urlerror.HTTPError as error:
            raw = error.read(MAX_JSON_BYTES + 1)
            status = error.code
        except (OSError, urlerror.URLError) as error:
            raise MatchedControlPhysicalError(
                f"HTTP {method} {endpoint} failed: {error}"
            ) from error
        if len(raw) > MAX_JSON_BYTES:
            raise MatchedControlPhysicalError("device JSON response is too large")
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MatchedControlPhysicalError(
                "device response is not UTF-8 JSON"
            ) from error
        if not isinstance(decoded, Mapping):
            raise MatchedControlPhysicalError("device response root is not an object")
        return HttpResponse(status, decoded)

    return request


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command")
    describe_parser = commands.add_parser("describe", allow_abbrev=False)
    describe_parser.add_argument("--release", type=Path, required=True)
    authorize = commands.add_parser("authorize", allow_abbrev=False)
    authorize.add_argument("--release", type=Path, required=True)
    authorize.add_argument("--profile", choices=contract.PROFILES, required=True)
    authorize.add_argument("--ordinal", type=int, choices=(1, 2), required=True)
    authorize.add_argument("--temperature-c", required=True)
    authorize.add_argument("--diagnostic", type=Path, required=True)
    authorize.add_argument("--accept-c1-c8", required=True)
    authorize.add_argument("--confirm-initial-preconditions")
    authorize.add_argument(
        "--confirm-monitors",
        choices=(contract.OPERATOR_MONITORING_CONFIRMATION,),
        required=True,
    )
    authorize.add_argument(
        "--claim-registry", type=Path, default=DEFAULT_CLAIM_REGISTRY
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
                control_acceptance=args.accept_c1_c8,
                initial_precondition=args.confirm_initial_preconditions,
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
                    "treatment_release_id": context.root["pinned_treatment_release"][
                        "release_id"
                    ],
                    "compiled_trace_audit_id": context.root[
                        "compiled_treatment_control_trace_binding"
                    ]["audit_id"],
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
                reservation.finalize(report)
            finally:
                reservation.close()
        else:
            diagnostic = _read_json(args.diagnostic, label="J2-OFF diagnostic")
            requester = _http_requester(args.base_url, args.timeout_s)
            temperature = _temperature(args.temperature_c, context, args.ordinal)
            diagnostic_sha = _validate_seal(diagnostic, label="J2-OFF diagnostic")
            action = context.action(args.ordinal)
            reservation = _reserve_output(
                args.output,
                label="matched-control physical-once result",
                binding={
                    "release_id": context.release_id,
                    "profile_id": context.profile_id,
                    "ordinal": args.ordinal,
                    "role": action["role"],
                    "hardware_action_id": action["hardware_action_id"],
                    "treatment_release_id": context.root["pinned_treatment_release"][
                        "release_id"
                    ],
                    "compiled_trace_audit_id": context.root[
                        "compiled_treatment_control_trace_binding"
                    ]["audit_id"],
                    "transaction_descriptor_sha256": action[
                        "transaction_descriptor_sha256"
                    ],
                    "operator_temperature_c": temperature,
                    "diagnostic_canonical_sha256": diagnostic_sha,
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
                except MatchedControlPhysicalError as error:
                    unknown = MatchedControlPhysicalUnknown(
                        "visible action completed but sealed result could not be "
                        "finalized; claim consumed and retry forbidden"
                    )
                    _best_effort_finalize_failure(
                        reservation, unknown, claim_may_be_consumed=True
                    )
                    raise unknown from error
            finally:
                reservation.close()
    except MatchedControlPhysicalUnknown as error:
        print(f"matched-control physical outcome UNKNOWN: {error}", file=sys.stderr)
        return 3
    except MatchedControlPhysicalError as error:
        print(f"matched-control physical-once error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
