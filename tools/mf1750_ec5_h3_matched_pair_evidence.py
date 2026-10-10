#!/usr/bin/env python3
"""Offline evidence gates for the C-first matched H3 treatment/control pair.

The module performs no device, serial, network, upload, or flash operation.  It
can finalize the C leg only after successful, separately claimed control and
control-recovery results.  It can then derive a non-authorizing T preparation
gate, and can finalize the pair only after successful, separately claimed H3
V4 treatment and treatment-recovery results.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import errno
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any, Final, Mapping, Sequence

from tools import mf1750_ec5_h3_matched_control_contract as contract
from tools import mf1750_ec5_h3_matched_control_physical_once as control_physical
from tools import mf1750_ec5_h3_matched_control_release as control_release
from tools import mf1750_ec5_runtime_lut_physical_once as treatment_physical
from tools import mf1750_ec5_runtime_lut_release as treatment_release


SCHEMA_VERSION: Final = 2
CONTROL_LEG_KIND: Final = "mf1750-ec5-h3-matched-c-first-control-leg-v2"
TREATMENT_GATE_KIND: Final = (
    "mf1750-ec5-h3-matched-c-first-treatment-preparation-gate-v2"
)
PAIR_KIND: Final = "mf1750-ec5-h3-matched-c-first-final-pair-evidence-v2"
MAX_JSON_BYTES: Final = 4_000_000
CONTROL_OBSERVATION: Final = "CONTROL_VISIBLE_RESULT_OBSERVED_AND_RECORDED"
TREATMENT_OBSERVATION: Final = "TREATMENT_VISIBLE_RESULT_OBSERVED_AND_RECORDED"
CLEAN_WHITE_OBSERVATION: Final = "CLEAN_WHITE_FULL_PANEL_NO_RESIDUAL_VISIBLE"
ELECTRICAL_OBSERVATION: Final = "ELECTRICAL_NORMAL_NO_RESET"
BALANCE_OBSERVATION: Final = "POWER_OFF_OR_BALANCE_INTERVAL_COMPLETED"
J2_OFF_OBSERVATION: Final = "J2_CONFIRMED_OFF_AFTER_RECOVERY"
PAIR_ORDER_ATTESTATION: Final = (
    "CONFIRM_C1_C2_COMPLETED_BEFORE_T1_T2__NO_AUTOMATIC_CHAINING"
)
PAIR_COMPARISONS: Final = (
    "VISIBLE_DIFFERENCE_RECORDED",
    "NO_DETECTABLE_DIFFERENCE_RECORDED",
)


class MatchedPairEvidenceError(ValueError):
    """A C-first evidence object or one of its sealed inputs differs."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_regular_bytes(path: Path, *, label: str) -> tuple[Path, bytes]:
    candidate = Path(path)
    try:
        before = candidate.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise MatchedPairEvidenceError(
                f"{label} must be a non-symlink regular file"
            )
        if before.st_size <= 0 or before.st_size > MAX_JSON_BYTES:
            raise MatchedPairEvidenceError(f"{label} size is invalid")
        payload = candidate.read_bytes()
        after = candidate.lstat()
    except OSError as error:
        raise MatchedPairEvidenceError(f"could not read {label}: {error}") from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or len(payload) != after.st_size:
        raise MatchedPairEvidenceError(f"{label} changed while read")
    return candidate.resolve(strict=True), payload


def _decode_json(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise MatchedPairEvidenceError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(value, Mapping):
        raise MatchedPairEvidenceError(f"{label} root must be an object")
    return value


def _read_json(path: Path, *, label: str) -> tuple[Path, bytes, Mapping[str, Any]]:
    resolved, payload = _read_regular_bytes(path, label=label)
    return resolved, payload, _decode_json(payload, label=label)


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    root = deepcopy(dict(unsigned))
    root["integrity"] = {
        "algorithm": "sha256",
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
        "canonical_sha256": contract.sha256(root),
    }
    return root


def _validate_seal(value: Mapping[str, Any], *, label: str) -> str:
    integrity = value.get("integrity")
    if not isinstance(integrity, Mapping):
        raise MatchedPairEvidenceError(f"{label} is not sealed")
    expected = _seal({key: item for key, item in value.items() if key != "integrity"})[
        "integrity"
    ]
    if dict(integrity) != expected:
        raise MatchedPairEvidenceError(f"{label} integrity mismatch")
    return str(integrity["canonical_sha256"])


def _record(path: Path, payload: bytes, canonical_sha256: str) -> dict[str, Any]:
    return {
        "path": str(path),
        "bytes": len(payload),
        "sha256": contract.sha256(payload),
        "canonical_sha256": canonical_sha256,
    }


def _action(root: Mapping[str, Any], ordinal: int) -> Mapping[str, Any]:
    actions = root["profile_contract"]["actions"]
    selected = [item for item in actions if item.get("ordinal") == ordinal]
    if len(selected) != 1:
        raise MatchedPairEvidenceError(f"release has no unique ordinal {ordinal}")
    return selected[0]


def _validate_claim(
    result: Mapping[str, Any],
    action: Mapping[str, Any],
    *,
    claim_schema_version: int,
    claim_kind: str,
    label: str,
    extra_expected: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    path_value = result.get("claim_file")
    if not isinstance(path_value, str):
        raise MatchedPairEvidenceError(f"{label} claim path is absent")
    path, payload, claim = _read_json(Path(path_value), label=f"{label} claim")
    canonical = _validate_seal(claim, label=f"{label} claim")
    expected = {
        "schema_version": claim_schema_version,
        "kind": claim_kind,
        "release_id": result["release_id"],
        "profile_id": result["profile_id"],
        "ordinal": result["ordinal"],
        "role": action["role"],
        "hardware_action_id": action["hardware_action_id"],
        "operator_temperature_c": result["operator_temperature_c"],
        "state": "permanently_consumed_do_not_retry",
        "created_before_network": True,
    }
    expected.update(dict(extra_expected or {}))
    for key, wanted in expected.items():
        if claim.get(key) != wanted:
            raise MatchedPairEvidenceError(f"{label} claim {key} differs")
    for key in ("authorization_sha256", "diagnostic_canonical_sha256"):
        value = claim.get(key)
        if not isinstance(value, str) or len(value) != 64:
            raise MatchedPairEvidenceError(f"{label} claim {key} is invalid")
    if str(path) != path_value:
        raise MatchedPairEvidenceError(f"{label} result claim path differs")
    if contract.sha256(payload) != result.get("claim_file_sha256"):
        raise MatchedPairEvidenceError(f"{label} claim whole-file hash differs")
    return _record(path, payload, canonical), str(claim["diagnostic_canonical_sha256"])


def _validate_result_common(
    result: Mapping[str, Any],
    root: Mapping[str, Any],
    ordinal: int,
    *,
    result_schema_version: int,
    result_kind: str,
    label: str,
) -> Mapping[str, Any]:
    canonical = _validate_seal(result, label=label)
    action = _action(root, ordinal)
    expected = {
        "schema_version": result_schema_version,
        "kind": result_kind,
        "release_id": root["release_id"],
        "profile_id": root["profile_id"],
        "ordinal": ordinal,
        "role": action["role"],
        "hardware_action_id": action["hardware_action_id"],
        "operator_j2_assertion": "ON",
        "j2_is_device_measured": False,
        "operator_monitoring_state": contract.OPERATOR_MONITORING_CONFIRMATION,
        "preflight_get_requests_after_claim": 4,
        "arm_posts": 1,
        "execute_posts": 1,
        "visible_refreshes": 1,
        "outcome": "success",
        "retry_allowed": False,
        "automatic_chaining_performed": False,
        "automatic_recovery_performed": False,
        "profile_switch_performed": False,
    }
    for key, wanted in expected.items():
        if result.get(key) != wanted:
            raise MatchedPairEvidenceError(f"{label} {key} differs")
    temperature = result.get("operator_temperature_c")
    if not isinstance(temperature, str):
        raise MatchedPairEvidenceError(f"{label} temperature is absent")
    return {"canonical_sha256": canonical, "action": action}


def _validate_control_result(
    context: control_physical.ReleaseContext,
    *,
    ordinal: int,
    diagnostic_file: Path,
    result_file: Path,
) -> dict[str, Any]:
    result_path, result_payload, result = _read_json(
        result_file, label=f"control release ordinal {ordinal} result"
    )
    common = _validate_result_common(
        result,
        context.root,
        ordinal,
        result_schema_version=control_physical.SCHEMA_VERSION,
        result_kind=control_physical.RESULT_KIND,
        label=f"control release ordinal {ordinal} result",
    )
    claim_record, claim_diagnostic_canonical = _validate_claim(
        result,
        common["action"],
        claim_schema_version=control_physical.SCHEMA_VERSION,
        claim_kind=control_physical.CLAIM_KIND,
        label=f"control release ordinal {ordinal}",
        extra_expected={
            "treatment_release_id": context.root["pinned_treatment_release"][
                "release_id"
            ],
            "compiled_trace_audit_id": context.root[
                "compiled_treatment_control_trace_binding"
            ]["audit_id"],
        },
    )
    diagnostic_path, diagnostic_payload, diagnostic = _read_json(
        diagnostic_file, label=f"control release ordinal {ordinal} diagnostic"
    )
    diagnostic_canonical = _validate_seal(
        diagnostic, label=f"control release ordinal {ordinal} diagnostic"
    )
    try:
        diagnostic_boot_nonce = control_physical.validate_diagnostic(
            context,
            ordinal,
            diagnostic,
            operator_temperature_c=result["operator_temperature_c"],
        )
    except control_physical.MatchedControlPhysicalError as error:
        raise MatchedPairEvidenceError(
            f"control release ordinal {ordinal} diagnostic failed: {error}"
        ) from error
    if result.get("boot_nonce") != diagnostic_boot_nonce:
        raise MatchedPairEvidenceError(
            f"control release ordinal {ordinal} result boot nonce differs"
        )
    if diagnostic_canonical != claim_diagnostic_canonical:
        raise MatchedPairEvidenceError("control diagnostic/claim binding differs")
    return {
        "result": _record(result_path, result_payload, common["canonical_sha256"]),
        "claim": claim_record,
        "diagnostic": _record(
            diagnostic_path, diagnostic_payload, diagnostic_canonical
        ),
        "operator_temperature_c": result["operator_temperature_c"],
        "hardware_action_id": common["action"]["hardware_action_id"],
    }


def _control_release_context(
    release_file: Path,
) -> tuple[control_physical.ReleaseContext, dict[str, Any]]:
    path, payload = _read_regular_bytes(release_file, label="matched-control release")
    try:
        root = control_release.load_release(path)
        summary = control_release.validate_release(root)
        context = control_physical.context_from_root(root)
    except (
        control_release.MatchedControlReleaseError,
        control_physical.MatchedControlPhysicalError,
    ) as error:
        raise MatchedPairEvidenceError(
            f"matched-control release failed: {error}"
        ) from error
    return context, {
        "path": str(path),
        "bytes": len(payload),
        "sha256": contract.sha256(payload),
        "canonical_sha256": summary["canonical_sha256"],
        "release_id": summary["release_id"],
        "pinned_treatment_release_id": summary["pinned_treatment_release_id"],
        "compiled_trace_audit_id": summary["compiled_trace_audit_id"],
    }


def finalize_control_leg(
    *,
    matched_release_file: Path,
    control_diagnostic_file: Path,
    control_result_file: Path,
    recovery_diagnostic_file: Path,
    recovery_result_file: Path,
    control_observation: str,
    recovery_observation: str,
    electrical_observation: str,
    balance_observation: str,
    j2_off_observation: str,
    finalization_phrase: str,
) -> dict[str, Any]:
    """Return sealed C-leg evidence; never authorize or invoke T."""

    confirmations = {
        "control_observation": (control_observation, CONTROL_OBSERVATION),
        "recovery_observation": (recovery_observation, CLEAN_WHITE_OBSERVATION),
        "electrical_observation": (electrical_observation, ELECTRICAL_OBSERVATION),
        "balance_observation": (balance_observation, BALANCE_OBSERVATION),
        "j2_off_observation": (j2_off_observation, J2_OFF_OBSERVATION),
        "finalization_phrase": (
            finalization_phrase,
            contract.CONTROL_RECOVERY_FINALIZATION_PHRASE,
        ),
    }
    for label, (observed, expected) in confirmations.items():
        if observed != expected:
            raise MatchedPairEvidenceError(f"exact {label} differs")
    context, release_record = _control_release_context(matched_release_file)
    control_evidence = _validate_control_result(
        context,
        ordinal=1,
        diagnostic_file=control_diagnostic_file,
        result_file=control_result_file,
    )
    recovery_evidence = _validate_control_result(
        context,
        ordinal=2,
        diagnostic_file=recovery_diagnostic_file,
        result_file=recovery_result_file,
    )
    if control_evidence["claim"]["path"] == recovery_evidence["claim"]["path"]:
        raise MatchedPairEvidenceError("control and recovery claims are not distinct")
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": CONTROL_LEG_KIND,
        "campaign_id": contract.CAMPAIGN_ID,
        "profile_id": contract.PROFILE_ID,
        "matched_control_release": release_record,
        "matched_control_contract_id": context.root["contract_id"],
        "pinned_treatment_release_id": release_record["pinned_treatment_release_id"],
        "compiled_trace_audit_id": release_record["compiled_trace_audit_id"],
        "pair_stage_order_completed": [1, 2],
        "control": control_evidence,
        "control_recovery": recovery_evidence,
        "control_temperature_c": control_evidence["operator_temperature_c"],
        "operator_confirmations": {
            key: observed for key, (observed, _) in confirmations.items()
        },
        "initial_clean_white_is_treatment_finalized_evidence": False,
        "control_and_recovery_success_required": True,
        "control_and_recovery_success": True,
        "recovery_is_containment_not_treatment_authorization": True,
        "control_stage_order_is_operator_attested_not_clock_proven": True,
        "treatment_preparation_gate_eligible": True,
        "treatment_live_authorized": False,
        "automatic_chaining_performed": False,
        "retry_allowed": False,
        "device_io_performed_by_finalizer": False,
        "network_io_performed_by_finalizer": False,
        "visible_refreshes_requested_by_finalizer": 0,
    }
    unsigned["control_leg_id"] = contract.sha256(unsigned)
    return _seal(unsigned)


def validate_control_leg(root: Mapping[str, Any]) -> dict[str, Any]:
    canonical = _validate_seal(root, label="control-leg evidence")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != CONTROL_LEG_KIND
    ):
        raise MatchedPairEvidenceError("control-leg schema/kind differs")
    confirmations = root.get("operator_confirmations")
    if not isinstance(confirmations, Mapping):
        raise MatchedPairEvidenceError("control-leg confirmations are absent")
    release_record = root.get("matched_control_release")
    control_evidence = root.get("control")
    recovery_evidence = root.get("control_recovery")
    if not all(
        isinstance(value, Mapping)
        for value in (release_record, control_evidence, recovery_evidence)
    ):
        raise MatchedPairEvidenceError("control-leg file bindings are absent")
    rebuilt = finalize_control_leg(
        matched_release_file=Path(str(release_record["path"])),
        control_diagnostic_file=Path(str(control_evidence["diagnostic"]["path"])),
        control_result_file=Path(str(control_evidence["result"]["path"])),
        recovery_diagnostic_file=Path(str(recovery_evidence["diagnostic"]["path"])),
        recovery_result_file=Path(str(recovery_evidence["result"]["path"])),
        control_observation=str(confirmations.get("control_observation")),
        recovery_observation=str(confirmations.get("recovery_observation")),
        electrical_observation=str(confirmations.get("electrical_observation")),
        balance_observation=str(confirmations.get("balance_observation")),
        j2_off_observation=str(confirmations.get("j2_off_observation")),
        finalization_phrase=str(confirmations.get("finalization_phrase")),
    )
    if contract.canonical_json_bytes(rebuilt) != contract.canonical_json_bytes(root):
        raise MatchedPairEvidenceError(
            "control-leg evidence differs from deep reconstruction"
        )
    return {
        "valid": True,
        "canonical_sha256": canonical,
        "control_leg_id": root["control_leg_id"],
        "control_temperature_c": root["control_temperature_c"],
        "matched_control_contract_id": root["matched_control_contract_id"],
        "pinned_treatment_release_id": root["pinned_treatment_release_id"],
        "treatment_live_authorized": False,
    }


def load_control_leg(path: Path) -> dict[str, Any]:
    _, _, root = _read_json(path, label="control-leg evidence")
    validate_control_leg(root)
    return dict(root)


def treatment_preparation_gate(
    *,
    control_leg_file: Path,
    treatment_release_file: Path,
    operator_temperature_c: str,
) -> dict[str, Any]:
    """Validate that C is complete and T may begin its own fresh gates."""

    leg_path, leg_payload, leg = _read_json(
        control_leg_file, label="control-leg evidence"
    )
    leg_summary = validate_control_leg(leg)
    treatment_path, treatment_payload = _read_regular_bytes(
        treatment_release_file, label="pinned treatment release"
    )
    try:
        treatment_root = treatment_release.load_release(treatment_path)
        treatment_summary = treatment_release.validate_release(treatment_root)
    except treatment_release.RuntimeLutReleaseError as error:
        raise MatchedPairEvidenceError(
            f"pinned treatment release failed: {error}"
        ) from error
    if (
        treatment_summary["release_id"] != contract.PINNED_TREATMENT_RELEASE_ID
        or treatment_summary["canonical_sha256"]
        != contract.PINNED_TREATMENT_RELEASE_CANONICAL_SHA256
        or contract.sha256(treatment_payload)
        != contract.PINNED_TREATMENT_RELEASE_FILE_SHA256
        or leg_summary["pinned_treatment_release_id"] != treatment_summary["release_id"]
    ):
        raise MatchedPairEvidenceError("treatment identity differs from C-leg pin")
    if operator_temperature_c != leg_summary["control_temperature_c"]:
        raise MatchedPairEvidenceError(
            "treatment temperature must exactly equal C temperature at 0.1 C"
        )
    treatment_action = _action(treatment_root, 1)
    treatment_bindings = [
        item
        for item in treatment_root["action_artifact_bindings"]
        if item.get("ordinal") == 1
    ]
    if len(treatment_bindings) != 1:
        raise MatchedPairEvidenceError(
            "treatment release has no unique runtime artifact binding"
        )
    treatment_binding = treatment_bindings[0]
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": TREATMENT_GATE_KIND,
            "control_leg": _record(
                leg_path, leg_payload, leg_summary["canonical_sha256"]
            ),
            "control_leg_id": leg_summary["control_leg_id"],
            "matched_control_contract_id": leg_summary["matched_control_contract_id"],
            "treatment_release": {
                "path": str(treatment_path),
                "bytes": len(treatment_payload),
                "sha256": contract.sha256(treatment_payload),
                "canonical_sha256": treatment_summary["canonical_sha256"],
                "release_id": treatment_summary["release_id"],
            },
            "treatment_contract_id": treatment_root["contract_id"],
            "treatment_action_binding": {
                "ordinal": 1,
                "hardware_action_id": treatment_action["hardware_action_id"],
                "transaction_descriptor_sha256": treatment_action[
                    "transaction_descriptor_sha256"
                ],
                "firmware_binary_sha256": treatment_binding["firmware_binary_sha256"],
                "firmware_elf_sha256": treatment_binding["firmware_elf_sha256"],
            },
            "exact_operator_temperature_c": operator_temperature_c,
            "pair_stage_order_completed": [1, 2],
            "next_pair_stage": 3,
            "fresh_treatment_j2_off_diagnostic_still_required": True,
            "independent_treatment_authorization_and_claim_still_required": True,
            "treatment_live_authorized": False,
            "c_first_workflow_requires_preclaim_facade": True,
            "legacy_generic_runner_physically_disabled": False,
            "gate_alone_proves_future_facade_use": False,
            "automatic_chaining_performed": False,
            "device_io_performed": False,
            "network_io_performed": False,
            "visible_refreshes": 0,
        }
    )


def validate_treatment_gate(root: Mapping[str, Any]) -> dict[str, Any]:
    """Deep-replay a treatment gate and all of its sealed file bindings."""

    canonical = _validate_seal(root, label="treatment preparation gate")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != TREATMENT_GATE_KIND
    ):
        raise MatchedPairEvidenceError("treatment gate schema/kind differs")
    control_leg = root.get("control_leg")
    treatment_record = root.get("treatment_release")
    temperature = root.get("exact_operator_temperature_c")
    if (
        not isinstance(control_leg, Mapping)
        or not isinstance(treatment_record, Mapping)
        or not isinstance(temperature, str)
    ):
        raise MatchedPairEvidenceError("treatment gate file bindings are absent")
    rebuilt = treatment_preparation_gate(
        control_leg_file=Path(str(control_leg["path"])),
        treatment_release_file=Path(str(treatment_record["path"])),
        operator_temperature_c=temperature,
    )
    if contract.canonical_json_bytes(rebuilt) != contract.canonical_json_bytes(root):
        raise MatchedPairEvidenceError(
            "treatment gate differs from deterministic deep reconstruction"
        )
    return {
        "valid": True,
        "canonical_sha256": canonical,
        "control_leg_id": root["control_leg_id"],
        "matched_control_contract_id": root["matched_control_contract_id"],
        "treatment_release_id": treatment_record["release_id"],
        "treatment_release_sha256": treatment_record["sha256"],
        "treatment_release_canonical_sha256": treatment_record["canonical_sha256"],
        "treatment_contract_id": root["treatment_contract_id"],
        "treatment_action_binding": dict(root["treatment_action_binding"]),
        "exact_operator_temperature_c": temperature,
        "next_pair_stage": 3,
        "treatment_live_authorized": False,
    }


def load_treatment_gate(path: Path) -> dict[str, Any]:
    _, _, root = _read_json(path, label="treatment preparation gate")
    validate_treatment_gate(root)
    return dict(root)


def _validate_treatment_result(
    context: treatment_physical.ReleaseContext,
    *,
    ordinal: int,
    diagnostic_file: Path,
    result_file: Path,
) -> dict[str, Any]:
    path, payload, result = _read_json(
        result_file, label=f"treatment ordinal {ordinal} result"
    )
    common = _validate_result_common(
        result,
        context.root,
        ordinal,
        result_schema_version=treatment_physical.SCHEMA_VERSION,
        result_kind=treatment_physical.RESULT_KIND,
        label=f"treatment ordinal {ordinal} result",
    )
    claim_record, claim_diagnostic_canonical = _validate_claim(
        result,
        common["action"],
        claim_schema_version=treatment_physical.SCHEMA_VERSION,
        claim_kind=treatment_physical.CLAIM_KIND,
        label=f"treatment ordinal {ordinal}",
    )
    diagnostic_path, diagnostic_payload, diagnostic = _read_json(
        diagnostic_file, label=f"treatment ordinal {ordinal} diagnostic"
    )
    diagnostic_canonical = _validate_seal(
        diagnostic, label=f"treatment ordinal {ordinal} diagnostic"
    )
    try:
        diagnostic_boot_nonce = treatment_physical.validate_diagnostic(
            context,
            ordinal,
            diagnostic,
            operator_temperature_c=result["operator_temperature_c"],
        )
    except treatment_physical.PhysicalOnceError as error:
        raise MatchedPairEvidenceError(
            f"treatment ordinal {ordinal} diagnostic failed: {error}"
        ) from error
    if result.get("boot_nonce") != diagnostic_boot_nonce:
        raise MatchedPairEvidenceError(
            f"treatment ordinal {ordinal} result boot nonce differs"
        )
    if diagnostic_canonical != claim_diagnostic_canonical:
        raise MatchedPairEvidenceError(
            f"treatment ordinal {ordinal} diagnostic/claim binding differs"
        )
    return {
        "result": _record(path, payload, common["canonical_sha256"]),
        "claim": claim_record,
        "diagnostic": _record(
            diagnostic_path, diagnostic_payload, diagnostic_canonical
        ),
        "operator_temperature_c": result["operator_temperature_c"],
        "hardware_action_id": common["action"]["hardware_action_id"],
    }


def finalize_pair(
    *,
    control_leg_file: Path,
    treatment_release_file: Path,
    treatment_diagnostic_file: Path,
    treatment_result_file: Path,
    treatment_recovery_diagnostic_file: Path,
    treatment_recovery_result_file: Path,
    treatment_observation: str,
    treatment_recovery_observation: str,
    electrical_observation: str,
    j2_off_observation: str,
    pair_order_attestation: str,
    comparison_outcome: str,
    finalization_phrase: str,
) -> dict[str, Any]:
    """Finalize the four-stage pair after both independent recoveries succeed."""

    if treatment_observation != TREATMENT_OBSERVATION:
        raise MatchedPairEvidenceError("exact treatment observation differs")
    if treatment_recovery_observation != CLEAN_WHITE_OBSERVATION:
        raise MatchedPairEvidenceError("exact treatment recovery observation differs")
    if electrical_observation != ELECTRICAL_OBSERVATION:
        raise MatchedPairEvidenceError("exact electrical observation differs")
    if j2_off_observation != J2_OFF_OBSERVATION:
        raise MatchedPairEvidenceError("exact J2-OFF observation differs")
    if pair_order_attestation != PAIR_ORDER_ATTESTATION:
        raise MatchedPairEvidenceError("exact C-first order attestation differs")
    if comparison_outcome not in PAIR_COMPARISONS:
        raise MatchedPairEvidenceError("comparison outcome is unsupported")
    if finalization_phrase != contract.PAIR_FINALIZATION_PHRASE:
        raise MatchedPairEvidenceError("exact pair finalization phrase differs")
    gate = treatment_preparation_gate(
        control_leg_file=control_leg_file,
        treatment_release_file=treatment_release_file,
        operator_temperature_c=load_control_leg(control_leg_file)[
            "control_temperature_c"
        ],
    )
    treatment_path, treatment_payload = _read_regular_bytes(
        treatment_release_file, label="pinned treatment release"
    )
    treatment_root = treatment_release.load_release(treatment_path)
    try:
        treatment_context = treatment_physical.context_from_root(treatment_root)
    except treatment_physical.PhysicalOnceError as error:
        raise MatchedPairEvidenceError(
            f"pinned treatment runner context failed: {error}"
        ) from error
    runtime = _validate_treatment_result(
        treatment_context,
        ordinal=1,
        diagnostic_file=treatment_diagnostic_file,
        result_file=treatment_result_file,
    )
    recovery = _validate_treatment_result(
        treatment_context,
        ordinal=2,
        diagnostic_file=treatment_recovery_diagnostic_file,
        result_file=treatment_recovery_result_file,
    )
    if runtime["operator_temperature_c"] != gate["exact_operator_temperature_c"]:
        raise MatchedPairEvidenceError(
            "treatment result temperature does not exactly match C temperature"
        )
    if runtime["claim"]["path"] == recovery["claim"]["path"]:
        raise MatchedPairEvidenceError("treatment and recovery claims are not distinct")
    interpretation = (
        "NO_DETECTABLE_INCREMENTAL_EFFECT"
        if comparison_outcome == "NO_DETECTABLE_DIFFERENCE_RECORDED"
        else (
            "INCREMENTAL_VISIBLE_EFFECT_OF_COMBINED_R20_R21_COMMAND_STREAM__"
            "NOT_ACCEPTANCE_OR_ABI_PROOF"
        )
    )
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": PAIR_KIND,
        "campaign_id": contract.CAMPAIGN_ID,
        "profile_id": contract.PROFILE_ID,
        "pair_stage_order_completed": [1, 2, 3, 4],
        "control_leg": gate["control_leg"],
        "control_leg_id": gate["control_leg_id"],
        "treatment_release": {
            "path": str(treatment_path),
            "bytes": len(treatment_payload),
            "sha256": contract.sha256(treatment_payload),
            "release_id": treatment_root["release_id"],
        },
        "treatment": runtime,
        "treatment_recovery": recovery,
        "exact_matched_temperature_c": gate["exact_operator_temperature_c"],
        "operator_confirmations": {
            "treatment_observation": treatment_observation,
            "treatment_recovery_observation": treatment_recovery_observation,
            "electrical_observation": electrical_observation,
            "j2_off_observation": j2_off_observation,
            "pair_order_attestation": pair_order_attestation,
            "comparison_outcome": comparison_outcome,
            "finalization_phrase": finalization_phrase,
        },
        "interpretation": interpretation,
        "initial_clean_white_was_treatment_finalized_evidence": False,
        "pair_order_is_operator_attested_not_clock_proven": True,
        "all_four_success_results_required": True,
        "all_four_success_results_validated": True,
        "attribution_or_lut_abi_proven": False,
        "treatment_preclaim_facade_use_cryptographically_proven": False,
        "retry_allowed": False,
        "automatic_chaining_performed": False,
        "device_io_performed_by_finalizer": False,
        "network_io_performed_by_finalizer": False,
        "visible_refreshes_requested_by_finalizer": 0,
    }
    unsigned["pair_evidence_id"] = contract.sha256(unsigned)
    return _seal(unsigned)


def validate_pair(root: Mapping[str, Any]) -> dict[str, Any]:
    """Deep-replay a finalized four-stage pair from its sealed file bindings."""

    canonical = _validate_seal(root, label="final pair evidence")
    if root.get("schema_version") != SCHEMA_VERSION or root.get("kind") != PAIR_KIND:
        raise MatchedPairEvidenceError("final pair schema/kind differs")
    control_leg = root.get("control_leg")
    treatment = root.get("treatment")
    recovery = root.get("treatment_recovery")
    treatment_release_record = root.get("treatment_release")
    confirmations = root.get("operator_confirmations")
    if not all(
        isinstance(value, Mapping)
        for value in (
            control_leg,
            treatment,
            recovery,
            treatment_release_record,
            confirmations,
        )
    ):
        raise MatchedPairEvidenceError("final pair file bindings are absent")
    rebuilt = finalize_pair(
        control_leg_file=Path(str(control_leg["path"])),
        treatment_release_file=Path(str(treatment_release_record["path"])),
        treatment_diagnostic_file=Path(str(treatment["diagnostic"]["path"])),
        treatment_result_file=Path(str(treatment["result"]["path"])),
        treatment_recovery_diagnostic_file=Path(str(recovery["diagnostic"]["path"])),
        treatment_recovery_result_file=Path(str(recovery["result"]["path"])),
        treatment_observation=str(confirmations.get("treatment_observation")),
        treatment_recovery_observation=str(
            confirmations.get("treatment_recovery_observation")
        ),
        electrical_observation=str(confirmations.get("electrical_observation")),
        j2_off_observation=str(confirmations.get("j2_off_observation")),
        pair_order_attestation=str(confirmations.get("pair_order_attestation")),
        comparison_outcome=str(confirmations.get("comparison_outcome")),
        finalization_phrase=str(confirmations.get("finalization_phrase")),
    )
    if contract.canonical_json_bytes(rebuilt) != contract.canonical_json_bytes(root):
        raise MatchedPairEvidenceError(
            "final pair evidence differs from deep reconstruction"
        )
    return {
        "valid": True,
        "canonical_sha256": canonical,
        "pair_evidence_id": root["pair_evidence_id"],
        "pair_stage_order_completed": root["pair_stage_order_completed"],
        "interpretation": root["interpretation"],
        "attribution_or_lut_abi_proven": False,
    }


def load_pair(path: Path) -> dict[str, Any]:
    _, _, root = _read_json(path, label="final pair evidence")
    validate_pair(root)
    return dict(root)


def _safe_output_target(path: Path) -> Path:
    target = Path(os.path.abspath(os.fspath(path)))
    parent = target.parent

    def inspect_chain() -> None:
        for candidate in reversed((parent, *parent.parents)):
            try:
                info = candidate.lstat()
            except FileNotFoundError:
                continue
            except OSError as error:
                raise MatchedPairEvidenceError(
                    f"could not inspect evidence output directory: {error}"
                ) from error
            if stat.S_ISLNK(info.st_mode):
                raise MatchedPairEvidenceError(
                    "evidence output directory chain contains a symlink"
                )
            if not stat.S_ISDIR(info.st_mode):
                raise MatchedPairEvidenceError(
                    "evidence output parent chain is not a directory"
                )

    inspect_chain()
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise MatchedPairEvidenceError(
            f"could not create evidence output directory: {error}"
        ) from error
    inspect_chain()
    try:
        existing = target.lstat()
    except FileNotFoundError:
        pass
    except OSError as error:
        raise MatchedPairEvidenceError(
            f"could not inspect evidence output: {error}"
        ) from error
    else:
        if stat.S_ISLNK(existing.st_mode):
            raise MatchedPairEvidenceError("evidence output must not be a symlink")
        raise MatchedPairEvidenceError("evidence output already exists")
    return target


def _fsync_directory_if_supported(path: Path) -> None:
    """Durably publish a link where the platform supports directory fsync."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        if error.errno in {
            errno.EACCES,
            errno.EBADF,
            errno.EINVAL,
            errno.ENOTSUP,
            getattr(errno, "EISDIR", -1),
        }:
            return
        raise MatchedPairEvidenceError(
            f"could not open evidence output directory for fsync: {error}"
        ) from error
    try:
        try:
            os.fsync(descriptor)
        except OSError as error:
            if error.errno not in {
                errno.EACCES,
                errno.EBADF,
                errno.EINVAL,
                errno.ENOTSUP,
            }:
                raise MatchedPairEvidenceError(
                    f"could not fsync evidence output directory: {error}"
                ) from error
    finally:
        os.close(descriptor)


def write_new(path: Path, value: Mapping[str, Any]) -> Path:
    """Atomically publish one immutable JSON file with O_EXCL semantics."""

    payload = contract.canonical_json_bytes(value) + b"\n"
    target = _safe_output_target(path)
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            written = handle.write(payload)
            if written != len(payload):
                raise MatchedPairEvidenceError("evidence output write was short")
            handle.flush()
            os.fsync(handle.fileno())
        info = temporary.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise MatchedPairEvidenceError("temporary evidence output is unsafe")
        os.link(temporary, target)
        temporary.unlink()
        temporary = None
        _fsync_directory_if_supported(target.parent)
    except FileExistsError as error:
        raise MatchedPairEvidenceError("evidence output already exists") from error
    except OSError as error:
        raise MatchedPairEvidenceError(f"could not write evidence: {error}") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    try:
        info = target.lstat()
        observed = target.read_bytes()
    except OSError as error:
        raise MatchedPairEvidenceError(
            f"could not verify evidence output: {error}"
        ) from error
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or observed != payload
    ):
        raise MatchedPairEvidenceError("evidence output verification differs")
    return target


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    finalize_control = commands.add_parser("finalize-control-leg", allow_abbrev=False)
    finalize_control.add_argument("--matched-release", type=Path, required=True)
    finalize_control.add_argument("--control-diagnostic", type=Path, required=True)
    finalize_control.add_argument("--control-result", type=Path, required=True)
    finalize_control.add_argument("--recovery-diagnostic", type=Path, required=True)
    finalize_control.add_argument("--recovery-result", type=Path, required=True)
    finalize_control.add_argument(
        "--control-observation", choices=(CONTROL_OBSERVATION,), required=True
    )
    finalize_control.add_argument(
        "--recovery-observation", choices=(CLEAN_WHITE_OBSERVATION,), required=True
    )
    finalize_control.add_argument(
        "--electrical-observation", choices=(ELECTRICAL_OBSERVATION,), required=True
    )
    finalize_control.add_argument(
        "--balance-observation", choices=(BALANCE_OBSERVATION,), required=True
    )
    finalize_control.add_argument(
        "--j2-off-observation", choices=(J2_OFF_OBSERVATION,), required=True
    )
    finalize_control.add_argument(
        "--finalization-phrase",
        choices=(contract.CONTROL_RECOVERY_FINALIZATION_PHRASE,),
        required=True,
    )
    finalize_control.add_argument("--output", type=Path, required=True)
    gate = commands.add_parser("treatment-gate", allow_abbrev=False)
    gate.add_argument("--control-leg", type=Path, required=True)
    gate.add_argument("--treatment-release", type=Path, required=True)
    gate.add_argument("--temperature-c", required=True)
    gate.add_argument("--output", type=Path, required=True)
    finalize_pair_parser = commands.add_parser("finalize-pair", allow_abbrev=False)
    finalize_pair_parser.add_argument("--control-leg", type=Path, required=True)
    finalize_pair_parser.add_argument("--treatment-release", type=Path, required=True)
    finalize_pair_parser.add_argument("--treatment-result", type=Path, required=True)
    finalize_pair_parser.add_argument(
        "--treatment-diagnostic", type=Path, required=True
    )
    finalize_pair_parser.add_argument(
        "--treatment-recovery-result", type=Path, required=True
    )
    finalize_pair_parser.add_argument(
        "--treatment-recovery-diagnostic", type=Path, required=True
    )
    finalize_pair_parser.add_argument(
        "--treatment-observation", choices=(TREATMENT_OBSERVATION,), required=True
    )
    finalize_pair_parser.add_argument(
        "--treatment-recovery-observation",
        choices=(CLEAN_WHITE_OBSERVATION,),
        required=True,
    )
    finalize_pair_parser.add_argument(
        "--electrical-observation", choices=(ELECTRICAL_OBSERVATION,), required=True
    )
    finalize_pair_parser.add_argument(
        "--j2-off-observation", choices=(J2_OFF_OBSERVATION,), required=True
    )
    finalize_pair_parser.add_argument(
        "--pair-order-attestation", choices=(PAIR_ORDER_ATTESTATION,), required=True
    )
    finalize_pair_parser.add_argument(
        "--comparison-outcome", choices=PAIR_COMPARISONS, required=True
    )
    finalize_pair_parser.add_argument(
        "--finalization-phrase",
        choices=(contract.PAIR_FINALIZATION_PHRASE,),
        required=True,
    )
    finalize_pair_parser.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate-control-leg", allow_abbrev=False)
    validate.add_argument("--control-leg", type=Path, required=True)
    validate_gate = commands.add_parser("validate-treatment-gate", allow_abbrev=False)
    validate_gate.add_argument("--treatment-gate", type=Path, required=True)
    validate_pair_parser = commands.add_parser("validate-pair", allow_abbrev=False)
    validate_pair_parser.add_argument("--pair", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        output: Path | None = None
        if args.command == "finalize-control-leg":
            report = finalize_control_leg(
                matched_release_file=args.matched_release,
                control_diagnostic_file=args.control_diagnostic,
                control_result_file=args.control_result,
                recovery_diagnostic_file=args.recovery_diagnostic,
                recovery_result_file=args.recovery_result,
                control_observation=args.control_observation,
                recovery_observation=args.recovery_observation,
                electrical_observation=args.electrical_observation,
                balance_observation=args.balance_observation,
                j2_off_observation=args.j2_off_observation,
                finalization_phrase=args.finalization_phrase,
            )
            output = args.output
        elif args.command == "treatment-gate":
            report = treatment_preparation_gate(
                control_leg_file=args.control_leg,
                treatment_release_file=args.treatment_release,
                operator_temperature_c=args.temperature_c,
            )
            output = args.output
        elif args.command == "finalize-pair":
            report = finalize_pair(
                control_leg_file=args.control_leg,
                treatment_release_file=args.treatment_release,
                treatment_diagnostic_file=args.treatment_diagnostic,
                treatment_result_file=args.treatment_result,
                treatment_recovery_diagnostic_file=(args.treatment_recovery_diagnostic),
                treatment_recovery_result_file=args.treatment_recovery_result,
                treatment_observation=args.treatment_observation,
                treatment_recovery_observation=args.treatment_recovery_observation,
                electrical_observation=args.electrical_observation,
                j2_off_observation=args.j2_off_observation,
                pair_order_attestation=args.pair_order_attestation,
                comparison_outcome=args.comparison_outcome,
                finalization_phrase=args.finalization_phrase,
            )
            output = args.output
        elif args.command == "validate-control-leg":
            report = validate_control_leg(load_control_leg(args.control_leg))
        elif args.command == "validate-treatment-gate":
            report = validate_treatment_gate(load_treatment_gate(args.treatment_gate))
        else:
            report = validate_pair(load_pair(args.pair))
        if output is not None:
            written = write_new(output, report)
            report = {
                "valid": True,
                "kind": report["kind"],
                "canonical_sha256": report["integrity"]["canonical_sha256"],
                "output": str(written),
                "device_io_performed_by_cli": False,
                "network_io_performed_by_cli": False,
                "visible_refreshes_requested_by_cli": 0,
                "live_authorized_by_cli": False,
            }
    except (
        KeyError,
        TypeError,
        MatchedPairEvidenceError,
        control_release.MatchedControlReleaseError,
        treatment_release.RuntimeLutReleaseError,
    ) as error:
        print(f"matched-pair evidence error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
