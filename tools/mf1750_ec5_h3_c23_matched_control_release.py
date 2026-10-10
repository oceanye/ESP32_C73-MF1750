#!/usr/bin/env python3
"""Materialize and deep-validate the WF23 C23 matched-control release.

The release binds the two dedicated C23 images, the exact sealed T23 V7
treatment release, the compiled C23/T23 trace audit, and every host source
needed by the later one-shot workflow.  It is offline and non-authorizing.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Final, Mapping, Sequence

from tools import mf1750_ec5_h3_c23_compiled_identity as compiled
from tools import mf1750_ec5_h3_c23_matched_control_contract as contract
from tools import mf1750_ec5_h3_c23_matched_trace_audit as trace_audit


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
SCHEMA_VERSION: Final = 2
KIND: Final = "mf1750-ec5-h3-c23-matched-no-r20-r21-profile-release-v2"
HOST_EXECUTION_BUNDLE_KIND: Final = (
    "mf1750-ec5-h3-c23-matched-control-host-execution-source-bundle"
)
HOST_EXECUTION_SOURCE_RELATIVE_PATHS: Final = (
    "tools/mf1750_ec5_h3_c23_matched_control_physical_once.py",
    "tools/mf1750_ec5_h3_c23_matched_control_release.py",
    "tools/mf1750_ec5_h3_c23_matched_pair_evidence.py",
    "tools/mf1750_ec5_h3_c23_first_treatment_once.py",
    "tools/mf1750_ec5_h3_c23_compiled_identity.py",
    "tools/mf1750_ec5_h3_c23_matched_control_contract.py",
    "tools/mf1750_ec5_h3_c23_matched_trace_audit.py",
    "tools/mf1750_ec5_h3_matched_control_physical_once.py",
    "tools/mf1750_ec5_h3_matched_control_release.py",
    "tools/mf1750_ec5_h3_matched_pair_evidence.py",
    "tools/mf1750_ec5_h3_c_first_treatment_once.py",
    "tools/mf1750_ec5_h3_matched_trace_audit.py",
    "tools/mf1750_ec5_runtime_lut_physical_once.py",
    "tools/mf1750_ec5_runtime_lut_release.py",
    "tools/mf1750_ec5_runtime_lut_compiled_identity.py",
    "tools/mf1750_ec5_runtime_lut_contract.py",
    "tools/mf1750_ec5_eightcode_atlas.py",
)


def _load_engine() -> Any:
    name = "tools._mf1750_ec5_h3_c23_matched_release_engine"
    path = REPO_ROOT / "tools" / "mf1750_ec5_h3_matched_control_release.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("could not load the frozen matched-release engine")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_engine = _load_engine()
MatchedControlReleaseError = _engine.MatchedControlReleaseError
_engine.contract = contract
_engine.compiled = SimpleNamespace(
    validate_image=compiled.validate_image,
    MatchedControlCompiledIdentityError=compiled.C23CompiledIdentityError,
)
_engine.trace_audit = trace_audit
_engine.KIND = KIND
_engine.HOST_EXECUTION_BUNDLE_KIND = HOST_EXECUTION_BUNDLE_KIND
_engine.HOST_EXECUTION_SOURCE_RELATIVE_PATHS = HOST_EXECUTION_SOURCE_RELATIVE_PATHS
_engine.HOST_EXECUTION_SOURCE_ROOT = REPO_ROOT


def host_execution_bundle() -> dict[str, Any]:
    return dict(_engine.host_execution_bundle())


def _c23_release_shape(raw: Mapping[str, Any]) -> dict[str, Any]:
    unsigned = deepcopy(
        {
            key: value
            for key, value in raw.items()
            if key not in {"integrity", "release_id"}
        }
    )
    layer = unsigned["c_first_treatment_operator_layer"]
    layer["intended_entry_point"] = "tools/mf1750_ec5_h3_c23_first_treatment_once.py"
    unsigned["claim_namespace"] = {
        "kind": "mf1750-ec5-h3-c23-matched-control-permanent-host-claim-v2",
        "registry": ".mf1750_ec5_h3_c23_matched_control_claims_v2",
        "reuses_empirical_h3_claim_kind": False,
        "reuses_empirical_h3_registry": False,
        "reuses_c20_claim_kind": False,
        "reuses_c20_registry": False,
    }
    prerequisites = unsigned["live_authorization_prerequisites"]
    prerequisites.pop("control_temperature_record_within_wf20_25_required", None)
    prerequisites["control_temperature_record_at_exact_c23_guard_required"] = True
    prerequisites["c23_control_leg_finalization_required_before_t23"] = True
    unsigned["release_id"] = contract.sha256(unsigned)
    return _engine._seal(unsigned)


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
    """Build a deterministic, non-authorizing C23 release offline."""

    raw = _engine.materialize_release(
        treatment_release_file=treatment_release_file,
        control_elf=control_elf,
        control_binary=control_binary,
        control_source=control_source,
        recovery_elf=recovery_elf,
        recovery_binary=recovery_binary,
        recovery_source=recovery_source,
    )
    root = _c23_release_shape(raw)
    if root["profile_id"] != contract.PROFILE_ID or root["kind"] != KIND:
        raise MatchedControlReleaseError("C23 release identity differs")
    return root


def validate_release(root: Mapping[str, Any]) -> dict[str, Any]:
    canonical = _engine._validate_seal(root)
    if root.get("schema_version") != SCHEMA_VERSION or root.get("kind") != KIND:
        raise MatchedControlReleaseError("C23 release schema/kind differs")
    if root.get("profile_id") != contract.PROFILE_ID:
        raise MatchedControlReleaseError("C23 release profile differs")
    if root.get("classification") != contract.CLASSIFICATION:
        raise MatchedControlReleaseError("C23 release classification differs")
    images = root.get("compiled_images")
    treatment = root.get("pinned_treatment_release")
    if not isinstance(images, Mapping) or set(images) != {
        "matched_no_r20_r21_control",
        "factory_otp_white",
    }:
        raise MatchedControlReleaseError("C23 compiled-image set differs")
    if not isinstance(treatment, Mapping):
        raise MatchedControlReleaseError("C23 treatment binding is absent")
    host_bundle = root.get("host_execution_bundle")
    if not isinstance(host_bundle, Mapping) or contract.canonical_json_bytes(
        host_bundle
    ) != contract.canonical_json_bytes(host_execution_bundle()):
        raise MatchedControlReleaseError("C23 host execution source bundle differs")
    stored_trace = root.get("compiled_treatment_control_trace_audit")
    trace_binding = root.get("compiled_treatment_control_trace_binding")
    if not isinstance(stored_trace, Mapping) or not isinstance(trace_binding, Mapping):
        raise MatchedControlReleaseError("C23 compiled trace audit/binding is absent")
    try:
        trace_canonical = trace_audit.validate_seal(stored_trace)
    except trace_audit.MatchedTraceAuditError as error:
        raise MatchedControlReleaseError(
            f"stored C23 compiled trace audit failed: {error}"
        ) from error
    if (
        stored_trace.get("profile_id") != contract.PROFILE_ID
        or stored_trace.get("classification") != contract.CONTROL_DESIGN
        or trace_binding.get("audit_id") != stored_trace.get("audit_id")
        or trace_binding.get("canonical_sha256") != trace_canonical
        or trace_binding.get("classification") != contract.CONTROL_DESIGN
        or trace_binding.get("strip_exact_four_upload_spans_equals_control") is not True
        or trace_binding.get("transitive_build_manifest_bound") is not True
        or trace_binding.get("T_equals_C_classification")
        != "NO_DETECTABLE_INCREMENTAL_EFFECT"
    ):
        raise MatchedControlReleaseError("C23 compiled trace binding differs")
    claim = root.get("claim_namespace")
    prerequisites = root.get("live_authorization_prerequisites")
    layer = root.get("c_first_treatment_operator_layer")
    if (
        not isinstance(claim, Mapping)
        or claim.get("reuses_c20_registry") is not False
        or not isinstance(prerequisites, Mapping)
        or prerequisites.get("control_temperature_record_at_exact_c23_guard_required")
        is not True
        or prerequisites.get("c23_control_leg_finalization_required_before_t23")
        is not True
        or not isinstance(layer, Mapping)
        or layer.get("intended_entry_point")
        != "tools/mf1750_ec5_h3_c23_first_treatment_once.py"
    ):
        raise MatchedControlReleaseError("C23 execution isolation differs")
    control_files = images["matched_no_r20_r21_control"]["firmware"]
    recovery_files = images["factory_otp_white"]["firmware"]
    rebuilt = materialize_release(
        treatment_release_file=Path(str(treatment["path"])),
        control_elf=Path(control_files["elf"]["path"]),
        control_binary=Path(control_files["binary"]["path"]),
        control_source=Path(control_files["transaction_source"]["path"]),
        recovery_elf=Path(recovery_files["elf"]["path"]),
        recovery_binary=Path(recovery_files["binary"]["path"]),
        recovery_source=Path(recovery_files["transaction_source"]["path"]),
    )
    if contract.canonical_json_bytes(rebuilt) != contract.canonical_json_bytes(root):
        raise MatchedControlReleaseError(
            "C23 release differs from deterministic deep reconstruction"
        )
    return {
        "valid": True,
        "profile_id": root["profile_id"],
        "release_id": root["release_id"],
        "canonical_sha256": canonical,
        "pinned_treatment_release_id": treatment["release_id"],
        "pinned_treatment_release_file_sha256": treatment["sha256"],
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
    root = dict(_engine._read_release(path))
    validate_release(root)
    return root


def write_new_release(path: Path, root: Mapping[str, Any]) -> None:
    validate_release(root)
    _engine.write_new_release(path, root)


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
    check = commands.add_parser("validate", allow_abbrev=False)
    check.add_argument("--release", type=Path, required=True)
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
        print(f"C23 matched-control release error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
