#!/usr/bin/env python3
"""Materialize/validate the C-first matched no-R20/R21 release offline.

Materialization binds two new, distinct one-action images to the exact frozen
WF20_25 H3 pinned treatment release and a typed compiled-trace comparison.  No
prior physical treatment result is accepted or required: initial white,
electrical state, monitoring, temperature, and J2-OFF remain unsatisfied live
preconditions.  This module cannot authorize, flash, upload, or contact a
device.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Any, Final, Mapping, Sequence

from tools import mf1750_ec5_h3_matched_control_compiled_identity as compiled
from tools import mf1750_ec5_h3_matched_control_contract as contract
from tools import mf1750_ec5_h3_matched_trace_audit as trace_audit
from tools import mf1750_ec5_runtime_lut_release as h3_release


SCHEMA_VERSION: Final = 2
KIND: Final = "mf1750-ec5-h3-matched-no-r20-r21-c-first-profile-release-v2"
MAX_RELEASE_BYTES: Final = 4_000_000
MAX_HOST_SOURCE_BYTES: Final = 2_000_000
HOST_EXECUTION_BUNDLE_KIND: Final = (
    "mf1750-ec5-h3-matched-control-host-execution-source-bundle"
)
HOST_EXECUTION_SOURCE_RELATIVE_PATHS: Final = (
    "tools/mf1750_ec5_h3_matched_control_physical_once.py",
    "tools/mf1750_ec5_h3_matched_control_release.py",
    "tools/mf1750_ec5_h3_matched_pair_evidence.py",
    "tools/mf1750_ec5_h3_c_first_treatment_once.py",
    "tools/mf1750_ec5_h3_matched_control_compiled_identity.py",
    "tools/mf1750_ec5_h3_matched_control_contract.py",
    "tools/mf1750_ec5_h3_matched_trace_audit.py",
    "tools/mf1750_ec5_runtime_lut_physical_once.py",
    "tools/mf1750_ec5_runtime_lut_release.py",
    "tools/mf1750_ec5_runtime_lut_compiled_identity.py",
    "tools/mf1750_ec5_runtime_lut_contract.py",
    "tools/mf1750_ec5_eightcode_atlas.py",
)
HOST_EXECUTION_SOURCE_ROOT: Path = contract.REPO_ROOT


class MatchedControlReleaseError(ValueError):
    """The matched-control release is incomplete or identity-mismatched."""


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    root = deepcopy(dict(unsigned))
    root["integrity"] = {
        "algorithm": "sha256",
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
        "canonical_sha256": contract.sha256(root),
    }
    return root


def _validate_seal(root: Mapping[str, Any]) -> str:
    integrity = root.get("integrity")
    if not isinstance(integrity, Mapping) or set(integrity) != {
        "algorithm",
        "scope",
        "canonical_sha256",
    }:
        raise MatchedControlReleaseError("release integrity object differs")
    expected = _seal({key: value for key, value in root.items() if key != "integrity"})[
        "integrity"
    ]
    if dict(integrity) != expected:
        raise MatchedControlReleaseError("release canonical integrity mismatch")
    return str(integrity["canonical_sha256"])


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_release(path: Path) -> Mapping[str, Any]:
    candidate = Path(path)
    try:
        before = candidate.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise MatchedControlReleaseError(
                "release must be a non-symlink regular file"
            )
        if before.st_size <= 0 or before.st_size > MAX_RELEASE_BYTES:
            raise MatchedControlReleaseError("release size is invalid")
        payload = candidate.read_bytes()
        after = candidate.lstat()
    except OSError as error:
        raise MatchedControlReleaseError(f"could not read release: {error}") from error
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
        raise MatchedControlReleaseError("release changed while being read")
    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise MatchedControlReleaseError("release is not strict UTF-8 JSON") from error
    if not isinstance(root, Mapping):
        raise MatchedControlReleaseError("release root must be an object")
    return root


def _host_source_record(relative_path: str) -> dict[str, Any]:
    if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
        raise MatchedControlReleaseError("host execution source path is not canonical")
    relative = PurePosixPath(relative_path)
    if (
        relative.is_absolute()
        or relative.as_posix() != relative_path
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise MatchedControlReleaseError("host execution source path is not canonical")
    root = Path(HOST_EXECUTION_SOURCE_ROOT)
    candidate = root.joinpath(*relative.parts)
    try:
        root_info = root.lstat()
        if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
            raise MatchedControlReleaseError(
                "host execution source root must be a non-symlink directory"
            )
        current = root
        for part in relative.parts:
            current = current / part
            if stat.S_ISLNK(current.lstat().st_mode):
                raise MatchedControlReleaseError(
                    f"host execution source path contains a symlink: {relative_path}"
                )
        resolved_root = root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=True)
        try:
            resolved_candidate.relative_to(resolved_root)
        except ValueError as error:
            raise MatchedControlReleaseError(
                f"host execution source escapes root: {relative_path}"
            ) from error
        before = candidate.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise MatchedControlReleaseError(
                f"host execution source is not regular: {relative_path}"
            )
        if before.st_size <= 0 or before.st_size > MAX_HOST_SOURCE_BYTES:
            raise MatchedControlReleaseError(
                f"host execution source size is invalid: {relative_path}"
            )
        payload = candidate.read_bytes()
        after = candidate.lstat()
    except MatchedControlReleaseError:
        raise
    except OSError as error:
        raise MatchedControlReleaseError(
            f"could not read host execution source {relative_path}: {error}"
        ) from error
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
        raise MatchedControlReleaseError(
            f"host execution source changed while read: {relative_path}"
        )
    return {
        "relative_path": relative_path,
        "bytes": len(payload),
        "sha256": contract.sha256(payload),
    }


def host_execution_bundle() -> dict[str, Any]:
    unsigned = {
        "schema_version": 1,
        "kind": HOST_EXECUTION_BUNDLE_KIND,
        "files": [
            _host_source_record(relative_path)
            for relative_path in HOST_EXECUTION_SOURCE_RELATIVE_PATHS
        ],
    }
    return {**unsigned, "canonical_sha256": contract.sha256(unsigned)}


def _same_file(left: str, right: str) -> bool:
    try:
        return os.path.samefile(Path(left), Path(right))
    except OSError as error:
        raise MatchedControlReleaseError(
            f"could not compare artifact paths: {error}"
        ) from error


def _ensure_new_distinct_images(
    control_image: Mapping[str, Any],
    recovery_image: Mapping[str, Any],
    treatment_root: Mapping[str, Any],
) -> None:
    control_firmware = control_image["firmware"]
    recovery_firmware = recovery_image["firmware"]
    for artifact in ("elf", "binary", "transaction_source"):
        left = control_firmware[artifact]
        right = recovery_firmware[artifact]
        if left["sha256"] == right["sha256"] or _same_file(left["path"], right["path"]):
            raise MatchedControlReleaseError(
                f"control and recovery {artifact} must be distinct"
            )
    old_images = treatment_root["compiled_images"].values()
    for label, selected in (
        ("control", control_firmware),
        ("recovery", recovery_firmware),
    ):
        for old in old_images:
            old_firmware = old["firmware"]
            for artifact in ("elf", "binary", "transaction_source"):
                if selected[artifact]["sha256"] == old_firmware[artifact]["sha256"]:
                    raise MatchedControlReleaseError(
                        f"{label} {artifact} reuses an H3 campaign artifact"
                    )
                if _same_file(
                    selected[artifact]["path"], old_firmware[artifact]["path"]
                ):
                    raise MatchedControlReleaseError(
                        f"{label} {artifact} reuses an H3 campaign path"
                    )


def _read_treatment_release_bytes(path: Path) -> tuple[Path, bytes]:
    candidate = Path(path)
    try:
        before = candidate.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise MatchedControlReleaseError(
                "treatment release must be a non-symlink regular file"
            )
        if before.st_size <= 0 or before.st_size > MAX_RELEASE_BYTES:
            raise MatchedControlReleaseError("treatment release size is invalid")
        payload = candidate.read_bytes()
        after = candidate.lstat()
    except OSError as error:
        raise MatchedControlReleaseError(
            f"could not read treatment release: {error}"
        ) from error
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
        raise MatchedControlReleaseError("treatment release changed while read")
    return candidate.resolve(strict=True), payload


def _treatment_binding(
    treatment_release_file: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        resolved, payload = _read_treatment_release_bytes(treatment_release_file)
        root = h3_release.load_release(resolved)
        summary = h3_release.validate_release(root)
    except h3_release.RuntimeLutReleaseError as error:
        raise MatchedControlReleaseError(
            f"pinned treatment release failed: {error}"
        ) from error
    expected = {
        "profile_id": contract.PROFILE_ID,
        "release_id": contract.PINNED_TREATMENT_RELEASE_ID,
        "canonical_sha256": contract.PINNED_TREATMENT_RELEASE_CANONICAL_SHA256,
        "runtime_binary_sha256": contract.PINNED_TREATMENT_RUNTIME_BINARY_SHA256,
        "runtime_elf_sha256": contract.PINNED_TREATMENT_RUNTIME_ELF_SHA256,
        "recovery_binary_sha256": contract.PINNED_TREATMENT_RECOVERY_BINARY_SHA256,
        "recovery_elf_sha256": contract.PINNED_TREATMENT_RECOVERY_ELF_SHA256,
    }
    for key, wanted in expected.items():
        if summary.get(key) != wanted:
            raise MatchedControlReleaseError(f"pinned treatment release {key} differs")
    file_sha = contract.sha256(payload)
    if file_sha != contract.PINNED_TREATMENT_RELEASE_FILE_SHA256:
        raise MatchedControlReleaseError(
            "pinned treatment release whole-file SHA differs"
        )
    binding = {
        "path": str(resolved),
        "bytes": len(payload),
        "sha256": file_sha,
        "canonical_sha256": summary["canonical_sha256"],
        "release_id": summary["release_id"],
        "profile_id": summary["profile_id"],
        "runtime_binary_sha256": summary["runtime_binary_sha256"],
        "runtime_elf_sha256": summary["runtime_elf_sha256"],
        "recovery_binary_sha256": summary["recovery_binary_sha256"],
        "recovery_elf_sha256": summary["recovery_elf_sha256"],
        "deep_validated": True,
        "physical_results_bound": False,
        "initial_clean_white_proven": False,
        "attribution_proven": False,
    }
    return root, binding


def materialize_release(
    *,
    treatment_release_file: Path,
    control_elf: Path,
    control_binary: Path,
    control_source: Path,
    recovery_elf: Path,
    recovery_binary: Path,
    recovery_source: Path,
) -> dict[str, Any]:
    """Build a deterministic, non-authorizing release after all offline gates."""

    frozen = contract.validate_contract()
    treatment_root, treatment_binding = _treatment_binding(treatment_release_file)
    try:
        control_image = compiled.validate_image(
            contract.PROFILE_ID,
            contract.ROLE_CONTROL,
            elf_file=control_elf,
            binary_file=control_binary,
            transaction_source_file=control_source,
        )
        recovery_image = compiled.validate_image(
            contract.PROFILE_ID,
            contract.ROLE_WHITE,
            elf_file=recovery_elf,
            binary_file=recovery_binary,
            transaction_source_file=recovery_source,
        )
    except compiled.MatchedControlCompiledIdentityError as error:
        raise MatchedControlReleaseError(
            f"compiled firmware identity gate failed: {error}"
        ) from error
    _ensure_new_distinct_images(control_image, recovery_image, treatment_root)
    try:
        compiled_trace = trace_audit.audit_pair(
            treatment_release_file=Path(treatment_binding["path"]),
            control_elf_file=control_elf,
            control_binary_file=control_binary,
            control_transaction_source_file=control_source,
        )
        trace_canonical_sha256 = trace_audit.validate_seal(compiled_trace)
    except trace_audit.MatchedTraceAuditError as error:
        raise MatchedControlReleaseError(
            f"compiled treatment/control trace gate failed: {error}"
        ) from error
    trace_identity = compiled_trace["identity"]
    trace_scope = compiled_trace["scope"]
    normalized_trace = compiled_trace["normalized_trace"]
    causal_scope = compiled_trace["causal_scope"]
    if (
        compiled_trace.get("schema_version") != trace_audit.SCHEMA_VERSION
        or compiled_trace.get("kind") != trace_audit.KIND
        or compiled_trace.get("valid") is not True
        or compiled_trace.get("classification") != contract.CONTROL_DESIGN
        or trace_identity["treatment_release"]["release_id"]
        != treatment_binding["release_id"]
        or trace_identity["control_elf"]["sha256"]
        != control_image["firmware"]["elf"]["sha256"]
        or trace_identity["control_binary"]["sha256"]
        != control_image["firmware"]["binary"]["sha256"]
        or trace_identity["control_transaction_descriptor_sha256"]
        != control_image["transaction_descriptor_sha256"]
        or trace_identity["control_hardware_action_id"]
        != control_image["hardware_action_id"]
        or normalized_trace.get("strip_exact_four_upload_spans_equals_control")
        is not True
        or normalized_trace.get("removed_upload_span_count") != 4
        or compiled_trace["compiled_common_functions"].get("all_normalized_equal")
        is not True
        or causal_scope.get("strict_payload_only_control") is not False
        or causal_scope.get("time_matched_control") is not False
        or causal_scope.get("dummy_or_empty_R20_R21_writes_in_control") is not False
        or causal_scope.get("treatment_only_SPI_bytes_per_controller") != 1505
        or causal_scope.get("treatment_only_source_yields_per_controller") != 5
        or causal_scope.get("T_equals_C_classification")
        != "NO_DETECTABLE_INCREMENTAL_EFFECT"
        or causal_scope.get("T_not_equal_C_proves_799_704_ABI") is not False
        or causal_scope.get("controller_acceptance_or_readback_proven") is not False
        or trace_scope.get("offline_read_only") is not True
        or any(
            trace_scope.get(key) is not False
            for key in (
                "hardware_accessed",
                "serial_or_COM_accessed",
                "device_network_accessed",
                "firmware_written_or_flashed",
                "visible_refresh_requested",
            )
        )
    ):
        raise MatchedControlReleaseError(
            "compiled treatment/control trace evidence differs"
        )

    identities = {
        contract.ROLE_CONTROL: control_image,
        contract.ROLE_WHITE: recovery_image,
    }
    action_bindings: list[dict[str, Any]] = []
    for action in frozen["actions"]:
        image = identities[action["role"]]
        device = contract.device_binding(contract.PROFILE_ID, action["role"])
        action_bindings.append(
            {
                "ordinal": action["ordinal"],
                "role": action["role"],
                "hardware_action_id": action["hardware_action_id"],
                "environment": image["environment"],
                "nvs_namespace": image["nvs_namespace"],
                "kind_prefix": device["kind_prefix"],
                "build_tag": device["build_tag"],
                "test_id": device["test_id"],
                "campaign_id": device["campaign_id"],
                "base_route": device["base_route"],
                "arm_intent": device["arm_intent"],
                "execute_intent": device["execute_intent"],
                "firmware_binary_sha256": image["firmware"]["binary"]["sha256"],
                "firmware_elf_sha256": image["firmware"]["elf"]["sha256"],
                "transaction_descriptor_sha256": image["transaction_descriptor_sha256"],
                "frame_sha256": action["payload_identity"]["frame_sha256"],
                "cs1_dtm_sha256": action["payload_identity"]["cs1_dtm_sha256"],
                "cs2_dtm_sha256": action["payload_identity"]["cs2_dtm_sha256"],
            }
        )

    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "classification": contract.CLASSIFICATION,
        "campaign_id": contract.CAMPAIGN_ID,
        "profile_id": contract.PROFILE_ID,
        "contract_id": frozen["contract_id"],
        "profile_contract": frozen,
        "pinned_treatment_release": treatment_binding,
        "c_first_temperature_policy": {
            "control_temperature_established_at_live_control_execution": True,
            "control_temperature_allowed_c": frozen[
                "experimental_fixed_temperature_guard_c"
            ],
            "guard_basis": frozen["temperature_guard_basis"],
            "vendor_filename_band_claim": False,
            "temperature_compatibility_qualified": False,
            "treatment_requires_exact_control_temperature_at_0p1_c": True,
            "exact_temperature_materialized_in_release": False,
            "temperature_match_is_safety_or_causality_proof": False,
        },
        "post_execute_silent_window": {
            "seconds": 30.0,
            "same_as_empirical_h3_runner": True,
            "no_request_during_window": True,
            "window_is_success_signal": False,
            "only_get_polling_allowed_after_window": True,
        },
        "compiled_images": {
            "matched_no_r20_r21_control": control_image,
            "factory_otp_white": recovery_image,
        },
        "compiled_treatment_control_trace_audit": compiled_trace,
        "compiled_treatment_control_trace_binding": {
            "audit_id": compiled_trace["audit_id"],
            "canonical_sha256": trace_canonical_sha256,
            "classification": contract.CONTROL_DESIGN,
            "strip_exact_four_upload_spans_equals_control": True,
            "removed_upload_span_count": 4,
            "transitive_build_manifest_bound": True,
            "compiled_common_functions_normalized_equal": True,
            "strict_payload_only_control": False,
            "time_matched_control": False,
            "T_equals_C_classification": "NO_DETECTABLE_INCREMENTAL_EFFECT",
            "audit_alone_authorizes_execution": False,
        },
        "host_execution_bundle": host_execution_bundle(),
        "c_first_treatment_operator_layer": {
            "intended_entry_point": ("tools/mf1750_ec5_h3_c_first_treatment_once.py"),
            "source_bytes_bound_in_host_execution_bundle": True,
            "hard_gates_invocations_made_through_facade": True,
            "validation_precedes_token_claim_and_network": True,
            "delegated_release_input": "private_byte_identical_snapshot",
            "original_release_path_reopened_by_delegate": False,
            "post_validation_original_path_replacement_rejected": True,
            "snapshot_deep_validated_before_delegate": True,
            "privileged_concurrent_snapshot_mutation_physically_prevented": False,
            "legacy_generic_runner_physically_disabled": False,
            "final_pair_can_cryptographically_prove_facade_use": False,
        },
        "action_artifact_bindings": action_bindings,
        "claim_namespace": {
            "kind": "mf1750-ec5-h3-matched-control-c-first-permanent-host-claim-v2",
            "registry": ".mf1750_ec5_h3_matched_control_claims_v2",
            "reuses_empirical_h3_claim_kind": False,
            "reuses_empirical_h3_registry": False,
        },
        "live_authorization_prerequisites": {
            "pinned_treatment_release_deep_validated": True,
            "pinned_treatment_release_revalidated_on_every_public_gate": True,
            "typed_treatment_control_trace_gate_required": True,
            "typed_treatment_control_trace_gate_materialized": True,
            "initial_clean_white_operator_confirmation_required": True,
            "initial_clean_white_is_treatment_finalized_evidence": False,
            "initial_electrical_normal_confirmation_required": True,
            "fresh_j2_off_diagnostic_per_action_required": True,
            "diagnostic_bound_authorization_required": True,
            "control_temperature_record_within_wf20_25_required": True,
            "later_treatment_exact_control_temperature_required": True,
            "c_first_treatment_preclaim_facade_required_by_workflow": True,
            "operator_monitoring_confirmation_required": (
                contract.OPERATOR_MONITORING_CONFIRMATION
            ),
            "initial_precondition_exact_phrase_required": True,
            "c1_c8_exact_acceptance_required": True,
            "accepted_at_materialization": False,
            "live_authorized": False,
        },
        "firmware_identities_materialized": True,
        "pinned_treatment_identity_materialized": True,
        "typed_treatment_control_trace_materialized": True,
        "execution_eligible_after_all_runner_gates": True,
        "two_independent_authorizations_required": True,
        "separate_flash_and_diagnostic_per_action_required": True,
        "automatic_chaining": False,
        "automatic_recovery": False,
        "retry": False,
        "profile_switch": False,
        "device_io_performed": False,
        "serial_io_performed": False,
        "network_io_performed": False,
        "upload_performed": False,
        "claims_created": False,
        "visible_refreshes": 0,
        "live_authorized": False,
    }
    unsigned["release_id"] = contract.sha256(unsigned)
    return _seal(unsigned)


def validate_release(root: Mapping[str, Any]) -> dict[str, Any]:
    canonical = _validate_seal(root)
    if root.get("schema_version") != SCHEMA_VERSION or root.get("kind") != KIND:
        raise MatchedControlReleaseError("release schema/kind differs")
    if root.get("profile_id") != contract.PROFILE_ID:
        raise MatchedControlReleaseError("release profile differs")
    images = root.get("compiled_images")
    treatment_binding = root.get("pinned_treatment_release")
    if not isinstance(images, Mapping) or set(images) != {
        "matched_no_r20_r21_control",
        "factory_otp_white",
    }:
        raise MatchedControlReleaseError("release compiled images differ")
    if not isinstance(treatment_binding, Mapping):
        raise MatchedControlReleaseError("release pinned-treatment binding is absent")
    host_bundle = root.get("host_execution_bundle")
    if not isinstance(host_bundle, Mapping):
        raise MatchedControlReleaseError("host execution source bundle is absent")
    if contract.canonical_json_bytes(host_bundle) != contract.canonical_json_bytes(
        host_execution_bundle()
    ):
        raise MatchedControlReleaseError("host execution source bundle differs")
    stored_trace = root.get("compiled_treatment_control_trace_audit")
    trace_binding = root.get("compiled_treatment_control_trace_binding")
    if not isinstance(stored_trace, Mapping) or not isinstance(trace_binding, Mapping):
        raise MatchedControlReleaseError("compiled trace audit/binding is absent")
    try:
        trace_canonical = trace_audit.validate_seal(stored_trace)
    except trace_audit.MatchedTraceAuditError as error:
        raise MatchedControlReleaseError(
            f"stored compiled trace audit failed: {error}"
        ) from error
    if (
        trace_binding.get("audit_id") != stored_trace.get("audit_id")
        or trace_binding.get("canonical_sha256") != trace_canonical
        or trace_binding.get("classification") != contract.CONTROL_DESIGN
        or trace_binding.get("strip_exact_four_upload_spans_equals_control") is not True
        or trace_binding.get("transitive_build_manifest_bound") is not True
        or trace_binding.get("T_equals_C_classification")
        != "NO_DETECTABLE_INCREMENTAL_EFFECT"
    ):
        raise MatchedControlReleaseError("compiled trace audit binding differs")
    control_files = images["matched_no_r20_r21_control"]["firmware"]
    recovery_files = images["factory_otp_white"]["firmware"]
    rebuilt = materialize_release(
        treatment_release_file=Path(str(treatment_binding["path"])),
        control_elf=Path(control_files["elf"]["path"]),
        control_binary=Path(control_files["binary"]["path"]),
        control_source=Path(control_files["transaction_source"]["path"]),
        recovery_elf=Path(recovery_files["elf"]["path"]),
        recovery_binary=Path(recovery_files["binary"]["path"]),
        recovery_source=Path(recovery_files["transaction_source"]["path"]),
    )
    if contract.canonical_json_bytes(rebuilt) != contract.canonical_json_bytes(root):
        raise MatchedControlReleaseError(
            "release differs from deterministic deep reconstruction"
        )
    return {
        "valid": True,
        "profile_id": root["profile_id"],
        "release_id": root["release_id"],
        "canonical_sha256": canonical,
        "pinned_treatment_release_id": treatment_binding["release_id"],
        "pinned_treatment_release_file_sha256": treatment_binding["sha256"],
        "control_binary_sha256": control_files["binary"]["sha256"],
        "control_elf_sha256": control_files["elf"]["sha256"],
        "recovery_binary_sha256": recovery_files["binary"]["sha256"],
        "recovery_elf_sha256": recovery_files["elf"]["sha256"],
        "compiled_trace_audit_id": stored_trace["audit_id"],
        "compiled_trace_canonical_sha256": trace_canonical,
        "host_execution_bundle_sha256": host_bundle["canonical_sha256"],
        "device_io_performed": False,
        "network_io_performed": False,
        "visible_refreshes": 0,
        "live_authorized": False,
    }


def load_release(path: Path) -> dict[str, Any]:
    root = dict(_read_release(path))
    validate_release(root)
    return root


def write_new_release(path: Path, root: Mapping[str, Any]) -> None:
    payload = contract.canonical_json_bytes(root) + b"\n"
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise MatchedControlReleaseError("release output already exists") from error
    except OSError as error:
        raise MatchedControlReleaseError(f"could not write release: {error}") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("materialize", allow_abbrev=False)
    build.add_argument("--treatment-release", type=Path, required=True)
    build.add_argument("--control-elf", type=Path, required=True)
    build.add_argument("--control-binary", type=Path, required=True)
    build.add_argument("--control-source", type=Path, required=True)
    build.add_argument("--recovery-elf", type=Path, required=True)
    build.add_argument("--recovery-binary", type=Path, required=True)
    build.add_argument("--recovery-source", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--release", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "materialize":
            root = materialize_release(
                treatment_release_file=args.treatment_release,
                control_elf=args.control_elf,
                control_binary=args.control_binary,
                control_source=args.control_source,
                recovery_elf=args.recovery_elf,
                recovery_binary=args.recovery_binary,
                recovery_source=args.recovery_source,
            )
            write_new_release(args.output, root)
            report = validate_release(root)
            report["release_file"] = str(args.output.resolve())
        else:
            report = validate_release(load_release(args.release))
    except (MatchedControlReleaseError, KeyError, TypeError) as error:
        print(f"matched-control release error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
