#!/usr/bin/env python3
"""C-first preclaim facade for the pinned empirical-H3 treatment action.

This is the intended and approved host entry point for stage 3 of the C-first
matched-pair workflow.  It deep-validates a finalized control leg and its
materialized treatment gate, then verifies the exact pinned release, contract,
compiled action artifacts, and 0.1 C temperature before delegating one command
to the frozen empirical-H3 runner through a private byte-identical release
snapshot.  Validation precedes authorization-token
derivation, claim creation, and construction or use of the HTTP requester.

The facade fixes the delegated ordinal to 1.  It never chains the independent
stage-4 recovery, retries an action, flashes firmware, or accesses a serial
port.  The pinned treatment release and its firmware/action identities are
not rewritten by this module.

Boundary: preserving the pinned release identity means its generic runner
remains directly callable outside this workflow.  This facade hard-gates every
invocation made through it, but cannot physically disable that generic CLI;
the final pair evidence therefore cannot cryptographically prove that stage 3
was invoked through this facade.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable, Final, Mapping, Sequence

from tools import mf1750_ec5_h3_matched_control_contract as matched_contract
from tools import mf1750_ec5_h3_matched_pair_evidence as pair_evidence
from tools import mf1750_ec5_runtime_lut_contract as treatment_contract
from tools import mf1750_ec5_runtime_lut_physical_once as treatment_physical
from tools import mf1750_ec5_runtime_lut_release as treatment_release


TREATMENT_ORDINAL: Final = 1
PRECLAIM_VALIDATION_KIND: Final = (
    "mf1750-ec5-h3-c-first-treatment-preclaim-validation-v1"
)


class CFirstTreatmentGateError(ValueError):
    """The C-first gate does not bind the exact delegated treatment action."""


def _treatment_action_binding(
    context: treatment_physical.ReleaseContext,
) -> dict[str, Any]:
    action = context.action(TREATMENT_ORDINAL)
    binding = context.binding(TREATMENT_ORDINAL)
    return {
        "ordinal": TREATMENT_ORDINAL,
        "hardware_action_id": action["hardware_action_id"],
        "transaction_descriptor_sha256": action["transaction_descriptor_sha256"],
        "firmware_binary_sha256": binding["firmware_binary_sha256"],
        "firmware_elf_sha256": binding["firmware_elf_sha256"],
    }


def validate_preclaim_gate(
    *,
    treatment_gate_file: Path,
    treatment_release_file: Path,
    operator_temperature_c: str,
) -> dict[str, Any]:
    """Return a sealed offline receipt after deep validation of every binding."""

    try:
        gate_path, gate_payload, gate = pair_evidence._read_json(  # noqa: SLF001
            treatment_gate_file, label="C-first treatment preparation gate"
        )
        gate_summary = pair_evidence.validate_treatment_gate(gate)
        release_path, release_payload = pair_evidence._read_regular_bytes(  # noqa: SLF001
            treatment_release_file, label="delegated pinned treatment release"
        )
        context = treatment_physical.load_release(release_path)
        release_summary = treatment_release.validate_release(context.root)
        expected_matched_contract = matched_contract.validate_contract()
        expected_treatment_contract = treatment_contract.validate_contract(
            matched_contract.PROFILE_ID
        )
        canonical_temperature = treatment_physical._temperature(  # noqa: SLF001
            operator_temperature_c, context, TREATMENT_ORDINAL
        )
    except (
        KeyError,
        TypeError,
        pair_evidence.MatchedPairEvidenceError,
        matched_contract.MatchedControlContractError,
        treatment_contract.RuntimeLutContractError,
        treatment_physical.PhysicalOnceError,
        treatment_release.RuntimeLutReleaseError,
    ) as error:
        raise CFirstTreatmentGateError(
            f"C-first preclaim input failed deep validation: {error}"
        ) from error

    release_record = gate.get("treatment_release")
    if not isinstance(release_record, Mapping):
        raise CFirstTreatmentGateError("gate treatment-release binding is absent")
    expected_release = {
        "sha256": treatment_contract.sha256(release_payload),
        "canonical_sha256": release_summary["canonical_sha256"],
        "release_id": release_summary["release_id"],
    }
    if any(release_record.get(key) != value for key, value in expected_release.items()):
        raise CFirstTreatmentGateError(
            "delegated treatment release identity differs from the gate"
        )
    if (
        gate_summary["matched_control_contract_id"]
        != expected_matched_contract["contract_id"]
    ):
        raise CFirstTreatmentGateError("matched-control contract identity differs")
    if (
        gate_summary["treatment_contract_id"]
        != expected_treatment_contract["contract_id"]
        or context.root.get("contract_id") != expected_treatment_contract["contract_id"]
    ):
        raise CFirstTreatmentGateError("treatment contract identity differs")
    if gate_summary["treatment_action_binding"] != _treatment_action_binding(context):
        raise CFirstTreatmentGateError(
            "compiled treatment action/artifact identity differs"
        )
    if canonical_temperature != gate_summary["exact_operator_temperature_c"]:
        raise CFirstTreatmentGateError(
            "delegated treatment temperature differs from the exact C temperature"
        )

    unsigned = {
        "schema_version": 1,
        "kind": PRECLAIM_VALIDATION_KIND,
        "treatment_gate": {
            "path": str(gate_path),
            "bytes": len(gate_payload),
            "sha256": treatment_contract.sha256(gate_payload),
            "canonical_sha256": gate_summary["canonical_sha256"],
            "control_leg_id": gate_summary["control_leg_id"],
        },
        "matched_control_contract_id": gate_summary["matched_control_contract_id"],
        "treatment_release": {
            "path": str(release_path),
            "bytes": len(release_payload),
            **expected_release,
        },
        "treatment_contract_id": gate_summary["treatment_contract_id"],
        "treatment_action_binding": gate_summary["treatment_action_binding"],
        "exact_operator_temperature_c": canonical_temperature,
        "pair_stage_order_completed": [1, 2],
        "next_pair_stage": 3,
        "delegated_ordinal": TREATMENT_ORDINAL,
        "validation_completed_before_token": True,
        "validation_completed_before_claim": True,
        "validation_completed_before_network": True,
        "facade_hard_gates_this_delegated_invocation": True,
        "legacy_generic_runner_physically_disabled": False,
        "final_pair_can_cryptographically_prove_facade_use": False,
        "token_derived": False,
        "claim_created": False,
        "network_requests": 0,
        "visible_refreshes": 0,
        "live_authorized": False,
        "automatic_chaining": False,
        "automatic_recovery": False,
        "retry": False,
    }
    return treatment_physical._seal(unsigned)  # noqa: SLF001


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--treatment-gate", type=Path, required=True)
    parser.add_argument("--temperature-c", required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)

    verify = commands.add_parser("verify", allow_abbrev=False)
    _add_common_arguments(verify)

    authorize = commands.add_parser("authorize", allow_abbrev=False)
    _add_common_arguments(authorize)
    authorize.add_argument("--diagnostic", type=Path, required=True)
    authorize.add_argument(
        "--claim-registry",
        type=Path,
        default=treatment_physical.DEFAULT_CLAIM_REGISTRY,
    )
    authorize.add_argument("--accept-u1-u7", required=True)
    authorize.add_argument(
        "--confirm-monitors",
        choices=(treatment_contract.OPERATOR_MONITORING_CONFIRMATION,),
        required=True,
    )

    diagnose = commands.add_parser("diagnose", allow_abbrev=False)
    _add_common_arguments(diagnose)
    diagnose.add_argument(
        "--screen-state", choices=(treatment_physical.SCREEN_INITIAL,), required=True
    )
    diagnose.add_argument("--confirm-j2", choices=("OFF",), required=True)
    diagnose.add_argument(
        "--confirm-monitors",
        choices=(treatment_contract.OPERATOR_MONITORING_CONFIRMATION,),
        required=True,
    )
    diagnose.add_argument("--base-url", required=True)
    diagnose.add_argument("--timeout-s", type=float, default=5.0)
    diagnose.add_argument("--output", type=Path, required=True)

    run = commands.add_parser("run", allow_abbrev=False)
    _add_common_arguments(run)
    run.add_argument("--confirm-j2", choices=("ON",), required=True)
    run.add_argument(
        "--confirm-monitors",
        choices=(treatment_contract.OPERATOR_MONITORING_CONFIRMATION,),
        required=True,
    )
    run.add_argument("--authorization", required=True)
    run.add_argument("--diagnostic", type=Path, required=True)
    run.add_argument("--base-url", required=True)
    run.add_argument("--timeout-s", type=float, default=5.0)
    run.add_argument(
        "--claim-registry",
        type=Path,
        default=treatment_physical.DEFAULT_CLAIM_REGISTRY,
    )
    run.add_argument(
        "--poll-count", type=int, default=treatment_physical.DEFAULT_POLL_COUNT
    )
    run.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=treatment_physical.DEFAULT_POLL_INTERVAL_SECONDS,
    )
    run.add_argument("--output", type=Path, required=True)
    return parser


def _delegate_argv(args: argparse.Namespace) -> list[str]:
    common = [
        args.command,
        "--release",
        str(args.release),
        "--ordinal",
        str(TREATMENT_ORDINAL),
        "--temperature-c",
        args.temperature_c,
    ]
    if args.command == "authorize":
        return [
            *common,
            "--profile",
            matched_contract.PROFILE_ID,
            "--diagnostic",
            str(args.diagnostic),
            "--claim-registry",
            str(args.claim_registry),
            "--accept-u1-u7",
            args.accept_u1_u7,
            "--confirm-monitors",
            args.confirm_monitors,
        ]
    if args.command == "diagnose":
        return [
            *common,
            "--screen-state",
            args.screen_state,
            "--confirm-j2",
            args.confirm_j2,
            "--confirm-monitors",
            args.confirm_monitors,
            "--base-url",
            args.base_url,
            "--timeout-s",
            str(args.timeout_s),
            "--output",
            str(args.output),
        ]
    return [
        *common,
        "--confirm-j2",
        args.confirm_j2,
        "--confirm-monitors",
        args.confirm_monitors,
        "--authorization",
        args.authorization,
        "--diagnostic",
        str(args.diagnostic),
        "--base-url",
        args.base_url,
        "--timeout-s",
        str(args.timeout_s),
        "--claim-registry",
        str(args.claim_registry),
        "--poll-count",
        str(args.poll_count),
        "--poll-interval-seconds",
        str(args.poll_interval_seconds),
        "--output",
        str(args.output),
    ]


def _delegate_with_validated_release_snapshot(
    args: argparse.Namespace,
    receipt: Mapping[str, Any],
    delegate: Callable[[Sequence[str] | None], int],
) -> int:
    """Delegate with a private byte-identical release snapshot, not a reopened input."""

    release_record = receipt.get("treatment_release")
    if not isinstance(release_record, Mapping):
        raise CFirstTreatmentGateError("validated treatment release record is absent")
    try:
        _, payload = pair_evidence._read_regular_bytes(  # noqa: SLF001
            args.release, label="delegated treatment release snapshot source"
        )
    except pair_evidence.MatchedPairEvidenceError as error:
        raise CFirstTreatmentGateError(
            f"could not re-read validated treatment release: {error}"
        ) from error
    if len(payload) != release_record.get("bytes") or treatment_contract.sha256(
        payload
    ) != release_record.get("sha256"):
        raise CFirstTreatmentGateError(
            "treatment release changed after preclaim validation"
        )

    temporary = tempfile.TemporaryDirectory(prefix="mf1750-c-first-release-")
    snapshot = Path(temporary.name) / "WF20_25-release.json"
    try:
        try:
            descriptor = os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                written = handle.write(payload)
                if written != len(payload):
                    raise CFirstTreatmentGateError(
                        "treatment release snapshot write was short"
                    )
                handle.flush()
                os.fsync(handle.fileno())
            snapshot_payload = snapshot.read_bytes()
        except OSError as error:
            raise CFirstTreatmentGateError(
                f"could not create treatment release snapshot: {error}"
            ) from error
        if snapshot_payload != payload:
            raise CFirstTreatmentGateError("treatment release snapshot bytes differ")
        try:
            snapshot_context = treatment_physical.load_release(snapshot)
            snapshot_summary = treatment_release.validate_release(snapshot_context.root)
        except (
            treatment_physical.PhysicalOnceError,
            treatment_release.RuntimeLutReleaseError,
        ) as error:
            raise CFirstTreatmentGateError(
                f"treatment release snapshot failed deep validation: {error}"
            ) from error
        if snapshot_summary["release_id"] != release_record.get(
            "release_id"
        ) or snapshot_summary["canonical_sha256"] != release_record.get(
            "canonical_sha256"
        ):
            raise CFirstTreatmentGateError(
                "treatment release snapshot identity differs"
            )
        delegated = _delegate_argv(args)
        delegated[delegated.index("--release") + 1] = str(snapshot)
        return delegate(delegated)
    finally:
        temporary.cleanup()


def main(
    argv: Sequence[str] | None = None,
    *,
    delegate: Callable[[Sequence[str] | None], int] = treatment_physical.main,
) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = validate_preclaim_gate(
            treatment_gate_file=args.treatment_gate,
            treatment_release_file=args.release,
            operator_temperature_c=args.temperature_c,
        )
    except CFirstTreatmentGateError as error:
        print(f"C-first treatment preclaim gate error: {error}", file=sys.stderr)
        return 2
    if args.command == "verify":
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
        return 0
    # No delegated argument is accepted as a pass-through.  The exact release,
    # temperature, and fixed ordinal below are the values validated above.
    try:
        return _delegate_with_validated_release_snapshot(args, receipt, delegate)
    except CFirstTreatmentGateError as error:
        print(f"C-first treatment preclaim gate error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
