#!/usr/bin/env python3
"""Materialize or validate one profile-specific empirical-H3 release.

Materialization is deliberately blocked until two exact, separate firmware
images exist: a runtime image containing one H3 atlas action and a factory-OTP
image containing one white action and no runtime payload.  The release also
binds every repository source used to validate or execute those actions.  This
tool performs no upload, serial, network, device, or display operation.
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

from tools import mf1750_ec5_runtime_lut_compiled_identity as compiled
from tools import mf1750_ec5_runtime_lut_contract as contract


SCHEMA_VERSION: Final = 3
KIND: Final = "mf1750-ec5-empirical-h3-profile-release"
MAX_RELEASE_BYTES: Final = 4_000_000
MAX_HOST_SOURCE_BYTES: Final = 1_000_000
HOST_EXECUTION_BUNDLE_KIND: Final = (
    "mf1750-ec5-empirical-h3-host-execution-source-bundle"
)
HOST_EXECUTION_SOURCE_RELATIVE_PATHS: Final = (
    "tools/mf1750_ec5_runtime_lut_physical_once.py",
    "tools/mf1750_ec5_runtime_lut_release.py",
    "tools/mf1750_ec5_runtime_lut_contract.py",
    "tools/mf1750_ec5_runtime_lut_compiled_identity.py",
    "tools/mf1750_ec5_eightcode_atlas.py",
)
# Kept separate from the frozen relative-path allowlist so tests can exercise
# byte drift and symlink rejection without changing any repository source.
HOST_EXECUTION_SOURCE_ROOT: Path = contract.REPO_ROOT


class RuntimeLutReleaseError(ValueError):
    """The release is incomplete, mutable, ambiguous, or identity-mismatched."""


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
        raise RuntimeLutReleaseError("release integrity object differs")
    expected = _seal({key: value for key, value in root.items() if key != "integrity"})[
        "integrity"
    ]
    if dict(integrity) != expected:
        raise RuntimeLutReleaseError("release canonical integrity mismatch")
    return str(integrity["canonical_sha256"])


def _read_release(path: Path) -> Mapping[str, Any]:
    candidate = Path(path)
    try:
        before = candidate.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise RuntimeLutReleaseError("release must be a non-symlink regular file")
        if before.st_size <= 0 or before.st_size > MAX_RELEASE_BYTES:
            raise RuntimeLutReleaseError("release size is invalid")
        payload = candidate.read_bytes()
        after = candidate.lstat()
    except OSError as error:
        raise RuntimeLutReleaseError(f"could not read release: {error}") from error
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(payload) != after.st_size:
        raise RuntimeLutReleaseError("release changed while being read")
    try:
        decoded = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise RuntimeLutReleaseError("release is not strict UTF-8 JSON") from error
    if not isinstance(decoded, Mapping):
        raise RuntimeLutReleaseError("release root must be an object")
    return decoded


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _host_source_record(relative_path: str) -> dict[str, Any]:
    if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
        raise RuntimeLutReleaseError("host execution source path is not canonical")
    relative = PurePosixPath(relative_path)
    if (
        relative.is_absolute()
        or relative.as_posix() != relative_path
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise RuntimeLutReleaseError("host execution source path is not canonical")

    root = Path(HOST_EXECUTION_SOURCE_ROOT)
    candidate = root.joinpath(*relative.parts)
    try:
        root_info = root.lstat()
        if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
            raise RuntimeLutReleaseError(
                "host execution source root must be a non-symlink directory"
            )
        current = root
        for part in relative.parts:
            current = current / part
            component = current.lstat()
            if stat.S_ISLNK(component.st_mode):
                raise RuntimeLutReleaseError(
                    f"host execution source path contains a symlink: {relative_path}"
                )
        resolved_root = root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=True)
        try:
            resolved_candidate.relative_to(resolved_root)
        except ValueError as error:
            raise RuntimeLutReleaseError(
                f"host execution source escapes its root: {relative_path}"
            ) from error
        before = candidate.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeLutReleaseError(
                f"host execution source must be a regular file: {relative_path}"
            )
        if before.st_size <= 0 or before.st_size > MAX_HOST_SOURCE_BYTES:
            raise RuntimeLutReleaseError(
                f"host execution source size is invalid: {relative_path}"
            )
        payload = candidate.read_bytes()
        after = candidate.lstat()
    except RuntimeLutReleaseError:
        raise
    except OSError as error:
        raise RuntimeLutReleaseError(
            f"could not read host execution source {relative_path}: {error}"
        ) from error
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(payload) != after.st_size:
        raise RuntimeLutReleaseError(
            f"host execution source changed while being read: {relative_path}"
        )
    return {
        "relative_path": relative_path,
        "bytes": len(payload),
        "sha256": contract.sha256(payload),
    }


def host_execution_bundle() -> dict[str, Any]:
    """Bind every in-repository Python source that can authorize one action."""

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
        raise RuntimeLutReleaseError(
            f"could not compare artifact paths: {error}"
        ) from error


def _ensure_two_images_are_distinct(
    runtime_identity: Mapping[str, Any], recovery_identity: Mapping[str, Any]
) -> None:
    runtime_firmware = runtime_identity["firmware"]
    recovery_firmware = recovery_identity["firmware"]
    for artifact in ("elf", "binary", "transaction_source"):
        left = runtime_firmware[artifact]
        right = recovery_firmware[artifact]
        if left["sha256"] == right["sha256"] or _same_file(left["path"], right["path"]):
            raise RuntimeLutReleaseError(
                f"runtime and recovery {artifact} must be exact distinct artifacts"
            )
    if runtime_identity["environment"] == recovery_identity["environment"]:
        raise RuntimeLutReleaseError("runtime and recovery environments must differ")
    if runtime_identity["nvs_namespace"] == recovery_identity["nvs_namespace"]:
        raise RuntimeLutReleaseError("runtime and recovery NVS namespaces must differ")


def _live_authorization_prerequisites(
    frozen: Mapping[str, Any],
) -> dict[str, Any]:
    risks = frozen["assumption_acceptance"]
    prior = frozen["current_prior"]
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-empirical-h3-live-authorization-prerequisites",
        "risk_declaration": {
            "unproven_assumptions": deepcopy(risks["assumptions"]),
            "u1_u7_contract_canonical_sha256": risks["canonical_sha256"],
            "required_exact_phrase": risks["required_exact_phrase"],
            "accepted_at_materialization": False,
            "acceptance_is_proof": False,
            "must_be_explicitly_reentered_after_fresh_diagnostic": True,
        },
        "operator_reported_prior_reference": {
            "prior_state_id": prior["prior_state_id"],
            "j2": prior["j2"],
            "screen": prior["screen"],
            "hardware_access_used_to_create_this_contract": prior[
                "hardware_access_used_to_create_this_contract"
            ],
            "accepted_at_materialization": False,
            "is_fresh_j2_off_diagnostic": False,
            "satisfies_live_diagnostic_gate": False,
        },
        "accepted_at_materialization": False,
        "live_authorized": False,
        "fresh_j2_off_diagnostic_required": True,
        "diagnostic_bound_authorization_v2_required": True,
        "explicit_single_profile_selection_required": True,
        "operator_temperature_required": True,
        "operator_monitoring_confirmation_required": (
            contract.OPERATOR_MONITORING_CONFIRMATION
        ),
    }


def materialize_release(
    profile_id: str,
    *,
    runtime_elf: Path,
    runtime_binary: Path,
    runtime_source: Path,
    generated_include: Path,
    recovery_elf: Path,
    recovery_binary: Path,
    recovery_source: Path,
) -> dict[str, Any]:
    """Build a deterministic release object after both image gates pass."""

    frozen = contract.validate_contract(profile_id)
    try:
        runtime_identity = compiled.validate_image(
            profile_id,
            contract.ROLE_RUNTIME,
            elf_file=runtime_elf,
            binary_file=runtime_binary,
            transaction_source_file=runtime_source,
            generated_include_file=generated_include,
        )
        recovery_identity = compiled.validate_image(
            profile_id,
            contract.ROLE_WHITE,
            elf_file=recovery_elf,
            binary_file=recovery_binary,
            transaction_source_file=recovery_source,
        )
    except compiled.RuntimeLutCompiledIdentityError as error:
        raise RuntimeLutReleaseError(
            f"compiled firmware identity gate failed: {error}"
        ) from error
    _ensure_two_images_are_distinct(runtime_identity, recovery_identity)

    action_bindings = []
    identities = {
        contract.ROLE_RUNTIME: runtime_identity,
        contract.ROLE_WHITE: recovery_identity,
    }
    for action in frozen["actions"]:
        image = identities[action["role"]]
        device = contract.device_binding(profile_id, action["role"])
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
                "generated_include_sha256": (
                    image["firmware"]["generated_include"]["sha256"]
                    if image["firmware"]["generated_include"] is not None
                    else None
                ),
                "frame_sha256": action["payload_identity"]["frame_sha256"],
                "cs1_dtm_sha256": action["payload_identity"]["cs1_dtm_sha256"],
                "cs2_dtm_sha256": action["payload_identity"]["cs2_dtm_sha256"],
            }
        )

    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "classification": contract.CLASSIFICATION,
        "campaign_id": frozen["campaign_id"],
        "profile_id": profile_id,
        "contract_id": frozen["contract_id"],
        "profile_contract": frozen,
        "live_authorization_prerequisites": _live_authorization_prerequisites(frozen),
        "compiled_images": {
            "runtime": runtime_identity,
            "factory_otp_white": recovery_identity,
        },
        "host_execution_bundle": host_execution_bundle(),
        "action_artifact_bindings": action_bindings,
        "firmware_identities_materialized": True,
        "execution_eligible_after_all_runner_gates": True,
        "live_authorized": False,
        "two_independent_authorizations_required": True,
        "runtime_failure_requires_j2_off_before_recovery_flash": True,
        "automatic_chaining": False,
        "automatic_recovery": False,
        "retry": False,
        "profile_switch": False,
        "device_io_performed": False,
        "serial_io_performed": False,
        "network_io_performed": False,
        "upload_performed": False,
        "visible_refreshes": 0,
    }
    unsigned["release_id"] = contract.sha256(unsigned)
    return _seal(unsigned)


def validate_release(root: Mapping[str, Any]) -> dict[str, Any]:
    """Deep-recompute a release from its exact referenced artifacts."""

    digest = _validate_seal(root)
    profile_id = root.get("profile_id")
    if profile_id not in contract.PROFILES:
        raise RuntimeLutReleaseError("release profile is unsupported")
    images = root.get("compiled_images")
    if not isinstance(images, Mapping):
        raise RuntimeLutReleaseError("release compiled images are absent")
    stored_host_bundle = root.get("host_execution_bundle")
    if not isinstance(stored_host_bundle, Mapping):
        raise RuntimeLutReleaseError("host execution source bundle is absent")
    prerequisites = root.get("live_authorization_prerequisites")
    if not isinstance(prerequisites, Mapping):
        raise RuntimeLutReleaseError("live authorization prerequisites are absent")
    if (
        prerequisites.get("accepted_at_materialization") is not False
        or prerequisites.get("live_authorized") is not False
    ):
        raise RuntimeLutReleaseError(
            "release must not record materialization-time live acceptance"
        )
    current_host_bundle = host_execution_bundle()
    if contract.canonical_json_bytes(
        stored_host_bundle
    ) != contract.canonical_json_bytes(current_host_bundle):
        raise RuntimeLutReleaseError("host execution source bundle differs")
    if set(images) != {"runtime", "factory_otp_white"}:
        raise RuntimeLutReleaseError("release must contain exactly two compiled images")
    runtime = images["runtime"]
    recovery = images["factory_otp_white"]
    if not isinstance(runtime, Mapping) or not isinstance(recovery, Mapping):
        raise RuntimeLutReleaseError("compiled image records must be objects")
    runtime_files = runtime.get("firmware")
    recovery_files = recovery.get("firmware")
    if not isinstance(runtime_files, Mapping) or not isinstance(
        recovery_files, Mapping
    ):
        raise RuntimeLutReleaseError("compiled image artifact records are absent")
    include = runtime_files.get("generated_include")
    if not isinstance(include, Mapping):
        raise RuntimeLutReleaseError("runtime generated include record is absent")

    rebuilt = materialize_release(
        str(profile_id),
        runtime_elf=Path(runtime_files["elf"]["path"]),
        runtime_binary=Path(runtime_files["binary"]["path"]),
        runtime_source=Path(runtime_files["transaction_source"]["path"]),
        generated_include=Path(include["path"]),
        recovery_elf=Path(recovery_files["elf"]["path"]),
        recovery_binary=Path(recovery_files["binary"]["path"]),
        recovery_source=Path(recovery_files["transaction_source"]["path"]),
    )
    if contract.canonical_json_bytes(rebuilt) != contract.canonical_json_bytes(root):
        raise RuntimeLutReleaseError(
            "release differs from deterministic reconstruction"
        )
    return {
        "valid": True,
        "profile_id": profile_id,
        "release_id": root["release_id"],
        "canonical_sha256": digest,
        "runtime_binary_sha256": runtime_files["binary"]["sha256"],
        "runtime_elf_sha256": runtime_files["elf"]["sha256"],
        "recovery_binary_sha256": recovery_files["binary"]["sha256"],
        "recovery_elf_sha256": recovery_files["elf"]["sha256"],
        "host_execution_bundle_sha256": root["host_execution_bundle"][
            "canonical_sha256"
        ],
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
        raise RuntimeLutReleaseError("release output already exists") from error
    except OSError as error:
        raise RuntimeLutReleaseError(f"could not write release: {error}") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("materialize", allow_abbrev=False)
    build.add_argument("--profile", choices=contract.PROFILES, required=True)
    build.add_argument("--runtime-elf", type=Path, required=True)
    build.add_argument("--runtime-binary", type=Path, required=True)
    build.add_argument("--runtime-source", type=Path, required=True)
    build.add_argument("--generated-include", type=Path, required=True)
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
                args.profile,
                runtime_elf=args.runtime_elf,
                runtime_binary=args.runtime_binary,
                runtime_source=args.runtime_source,
                generated_include=args.generated_include,
                recovery_elf=args.recovery_elf,
                recovery_binary=args.recovery_binary,
                recovery_source=args.recovery_source,
            )
            write_new_release(args.output, root)
            report = validate_release(root)
            report["release_file"] = str(args.output.resolve())
        else:
            root = load_release(args.release)
            report = validate_release(root)
    except (RuntimeLutReleaseError, KeyError, TypeError) as error:
        print(f"runtime-LUT release error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
