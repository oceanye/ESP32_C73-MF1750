#!/usr/bin/env python3
"""One-action-at-a-time runner for the factory-OTP 8x8 transition matrix.

The adapter reuses the audited COLOR_LAB HTTP/state engine but binds it under a
process-local lock to a distinct campaign, endpoint set, NVS identity, claim
registry, clean-white predecessor, and matrix-specific operator checklist.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any, Iterator, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_color_lab_physical_once as engine  # noqa: E402
from tools import mf1750_ec5_color_lab_recovery_contract as old_contract  # noqa: E402
from tools import mf1750_ec5_otp_transition_matrix_campaign as campaign  # noqa: E402
from tools import mf1750_ec5_otp_transition_matrix_contract as contract  # noqa: E402


DEVICE_KIND_PREFIX = "mf1750-ec5-otp-transition-matrix"
CLAIM_KIND = f"{DEVICE_KIND_PREFIX}-permanent-host-claim"
RESULT_KIND = f"{DEVICE_KIND_PREFIX}-physical-once-result"
OBSERVATION_KIND = f"{DEVICE_KIND_PREFIX}-manual-observation"
J2_OFF_DIAGNOSTIC_KIND = f"{DEVICE_KIND_PREFIX}-j2-off-diagnostic"
RECONCILIATION_KIND = f"{DEVICE_KIND_PREFIX}-late-terminal-readback-reconciliation"
OBSERVATION_TEMPLATE_KIND = f"{DEVICE_KIND_PREFIX}-observation-template"
CLAIM_REGISTRY_ID = "workspace-mf1750-ec5-otp-transition-matrix-claims-v1"
DEFAULT_CLAIM_REGISTRY = (
    REPO_ROOT / ".test-output" / "hardware" / ".mf1750_ec5_otp_transition_matrix_claims"
)

EXPECTED_CAMPAIGN_FILE_SHA256 = (
    "8dd9450a80880bad1756082942ffcb9b1af439d095424db6d1b4935dcdfff1c8"
)
EXPECTED_CAMPAIGN_CANONICAL_SHA256 = (
    "2d2abfc86134c98cf65831cb209e2dd86d41fa11edc9ba511bd944969a96e479"
)
EXPECTED_RELEASE_FILE_SHA256 = (
    "3f03a022b603fc312d836093b8c94cd6d6f0e7be5a3ff32f71337673cca263e8"
)
EXPECTED_RELEASE_CANONICAL_SHA256 = (
    "9c38297823699b43aa007e557cf5c435a30e9ebf4b8d2fb23d14a2c45eecc628"
)
EXPECTED_FIRMWARE_BINARY_SHA256 = (
    "cfba6e30772ce5f3f97cd7a88c5d75110c49dc9132c211127cc974b527754206"
)
EXPECTED_FIRMWARE_ELF_SHA256 = (
    "c153549a2ebb81d4187222cb8121fb350d9076dbe420c7e9ec8554b0ba81577e"
)

EXPECTED_ANCHOR_RESULT_SHA256 = (
    "ad9c9c78eb427d876284e658053c4869acf7baf3e57b4754b599a7b3255c8aaf"
)
EXPECTED_ANCHOR_OBSERVATION_SHA256 = (
    "79d8e885377fa141331cb8def8d39b70ec7d897723ce8a9a301bf9f1229514a7"
)
EXPECTED_ANCHOR_CLAIM_SHA256 = (
    "d40496d5e722ca9b4497b1cbfb5169beffa55958b9f4c4752a11ea375b886bd6"
)

PREVIEW_FILES = {
    contract.ROLE_PRIMER: REPO_ROOT
    / ".test-output/offline/MF1750_RUNTIME_WAVEFORM_PLACEHOLDER_CAMPAIGN_20260810_V1/preview/PSEUDOCOLOR-NOT-PHYSICAL-transition-primer.png",
    contract.ROLE_TARGET: REPO_ROOT
    / ".test-output/offline/MF1750_RUNTIME_WAVEFORM_PLACEHOLDER_CAMPAIGN_20260810_V1/preview/PSEUDOCOLOR-NOT-PHYSICAL-transition-target.png",
    contract.ROLE_WHITE: REPO_ROOT
    / ".test-output/offline/MF1750_RUNTIME_WAVEFORM_PLACEHOLDER_CAMPAIGN_20260810_V1/preview/PSEUDOCOLOR-NOT-PHYSICAL-white-recovery.png",
}

OtpTransitionMatrixPhysicalError = engine.ColorLabPhysicalError
ReleaseContext = engine.ReleaseContext
Preflight = engine.Preflight
Requester = engine.Requester
http_request = engine.http_request

_ENGINE_LOCK = engine._ENGINE_BINDING_LOCK


def _matrix_prior_gate(
    context: ReleaseContext,
    ordinal: int,
    *,
    prior_result_file: Path | None,
    prior_observation_file: Path | None,
    claim_registry: Path,
    confirm_no_intervening_visible_refresh: bool,
    j2_off_diagnostic_file: Path | None,
) -> dict[str, Any]:
    """Bind action 1 to clean white; bind actions 2/3 to the exact prior action."""

    if not confirm_no_intervening_visible_refresh:
        raise OtpTransitionMatrixPhysicalError(
            f"ordinal {ordinal} requires live no-intervening-refresh confirmation"
        )
    if ordinal == 1:
        if prior_result_file is not None or prior_observation_file is not None:
            raise OtpTransitionMatrixPhysicalError(
                "ordinal 1 accepts only the release-bound clean-white predecessor"
            )
        if j2_off_diagnostic_file is None:
            raise OtpTransitionMatrixPhysicalError(
                "ordinal 1 requires same-boot J2-off diagnostic evidence"
            )
        diagnostic = engine.validate_j2_off_diagnostic(
            context,
            j2_off_diagnostic_file,
            claim_registry=claim_registry,
        )
        anchor = context.release_root.get("predecessor_binding")
        if (
            not isinstance(anchor, Mapping)
            or anchor.get("action_id") != campaign.FIRST_PREDECESSOR_ACTION_ID
            or anchor.get("latest_visible_state") != "clean_full_white_factory_otp"
            or anchor.get("clean_white_confirmed") is not True
            or anchor.get("result", {}).get("file_sha256")
            != EXPECTED_ANCHOR_RESULT_SHA256
            or anchor.get("observation", {}).get("file_sha256")
            != EXPECTED_ANCHOR_OBSERVATION_SHA256
            or anchor.get("claim", {}).get("file_sha256")
            != EXPECTED_ANCHOR_CLAIM_SHA256
        ):
            raise OtpTransitionMatrixPhysicalError(
                "release-bound clean-white predecessor differs"
            )
        return {
            "kind": "exact_finalized_clean_white_anchor_and_j2_off_diagnostic",
            "predecessor_action_id": campaign.FIRST_PREDECESSOR_ACTION_ID,
            "anchor_result_file_sha256": EXPECTED_ANCHOR_RESULT_SHA256,
            "anchor_observation_file_sha256": EXPECTED_ANCHOR_OBSERVATION_SHA256,
            "anchor_claim_file_sha256": EXPECTED_ANCHOR_CLAIM_SHA256,
            "latest_visible_state": "clean_full_white_factory_otp",
            "j2_off_diagnostic": engine._file_reference(  # noqa: SLF001
                j2_off_diagnostic_file, label="J2-off diagnostic evidence"
            ),
            "required_same_boot_nonce": diagnostic["boot_nonce"],
            "live_no_intervening_visible_refresh_confirmed": True,
        }
    if j2_off_diagnostic_file is not None:
        raise OtpTransitionMatrixPhysicalError(
            "J2-off diagnostic evidence is accepted only for ordinal 1"
        )
    if prior_result_file is None or prior_observation_file is None:
        raise OtpTransitionMatrixPhysicalError(
            f"ordinal {ordinal} requires result and observation for ordinal {ordinal - 1}"
        )
    prior_result = engine.validate_result(
        context, prior_result_file, claim_registry=claim_registry
    )
    if (
        prior_result.get("ordinal") != ordinal - 1
        or prior_result.get("outcome") != "complete_pass"
    ):
        raise OtpTransitionMatrixPhysicalError(
            "prior result is not the exact previous complete action"
        )
    prior_observation = engine.validate_observation(
        context,
        prior_observation_file,
        result_file=prior_result_file,
        claim_registry=claim_registry,
    )
    if (
        prior_observation.get("ordinal") != ordinal - 1
        or prior_observation.get("sequence_gate_pass") is not True
    ):
        raise OtpTransitionMatrixPhysicalError(
            "prior observation does not unlock the next matrix action"
        )
    return {
        "kind": "exact_previous_otp_matrix_result_and_observation",
        "prior_ordinal": ordinal - 1,
        "result": engine._file_reference(  # noqa: SLF001
            prior_result_file, label="prior OTP matrix result"
        ),
        "observation": engine._file_reference(  # noqa: SLF001
            prior_observation_file, label="prior OTP matrix observation"
        ),
        "required_same_boot_nonce": prior_result["preflight"]["boot_nonce"],
        "live_no_intervening_visible_refresh_confirmed": True,
    }


def _matrix_describe(context: ReleaseContext, ordinal: int) -> dict[str, Any]:
    action = engine._action(context, ordinal)  # noqa: SLF001
    return {
        "release_execution_eligible": context.execution_eligible,
        "action": engine._action_reference(context, ordinal),  # noqa: SLF001
        "authorization": campaign.required_authorization(action),
        "requires_j2_off_diagnostic": ordinal == 1,
        "requires_prior_result_and_observation": ordinal > 1,
        "same_boot_and_no_intervening_refresh_required": True,
        "factory_otp_profile": True,
        "runtime_lut_or_waveform_changed": False,
        "safe_to_pause_after_observation": ordinal == 3,
        "automatic_chaining": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }


def _matrix_observation_template(
    context: ReleaseContext, ordinal: int
) -> dict[str, Any]:
    action = engine._action(context, ordinal)  # noqa: SLF001
    role = str(action["role"])
    preview_file = PREVIEW_FILES[role]
    preview_payload = engine._read(  # noqa: SLF001
        preview_file, label=f"{role} monitor preview"
    )
    common = [
        "reference_preview_checked",
        "display_matches_reference_layout",
        "left_right_mirrored_geometry_consistent",
        "no_unexpected_residual_or_damage",
        "electrical_normal",
        "temperature_c_10_to_45",
        "esp32_did_not_restart",
    ]
    if role == contract.ROLE_PRIMER:
        fields: dict[str, Any] = {
            "eight_old_state_rows_present_on_each_controller": None,
            "each_row_uniform_across_eight_columns": None,
            "cs1_cs2_semantic_old_states_match_after_axis_decode": None,
            "grid_edges_and_white_margin_clean": None,
        }
    elif role == contract.ROLE_TARGET:
        fields = {
            "interpretation": (
                "CS1 row=old0..7 column=new0..7; CS2 reverses both display axes"
            ),
            "candidate_cells_old_new": [],
            "visually_equivalent_cell_groups": [],
            "left_right_semantic_pairs_match": None,
            "old_state_dependent_colour_or_brightness_seen": None,
            "unexpected_ghost_or_damage_location": "",
        }
    else:
        fields = {
            "full_screen_clean_white": None,
            "all_matrix_cells_removed": None,
            "residual_or_outline_present": None,
            "residual_location_if_any": "",
        }
    return {
        "schema_version": engine.SCHEMA_VERSION,
        "kind": OBSERVATION_TEMPLATE_KIND,
        "action": engine._action_reference(context, ordinal),  # noqa: SLF001
        "preview": {
            "file": str(preview_file.resolve()),
            "bytes": len(preview_payload),
            "sha256": campaign.sha256(preview_payload),
            "notice": (
                "pseudocolor verifies code placement only; it does not predict "
                "reflective panel colour"
            ),
        },
        "common_checks": common,
        "role_observation_fields": fields,
        "one_operator_reply_may_cover_all_fields": True,
        "visible_refresh_authorized": False,
        "automatic_next_action_authorized": False,
    }


_ENGINE_BINDINGS: Mapping[str, Any] = {
    "campaign": campaign,
    "contract": contract,
    "DEVICE_KIND_PREFIX": DEVICE_KIND_PREFIX,
    "CLAIM_KIND": CLAIM_KIND,
    "RESULT_KIND": RESULT_KIND,
    "OBSERVATION_KIND": OBSERVATION_KIND,
    "J2_OFF_DIAGNOSTIC_KIND": J2_OFF_DIAGNOSTIC_KIND,
    "RECONCILIATION_KIND": RECONCILIATION_KIND,
    "OBSERVATION_TEMPLATE_KIND": OBSERVATION_TEMPLATE_KIND,
    "CLAIM_REGISTRY_ID": CLAIM_REGISTRY_ID,
    "DEFAULT_CLAIM_REGISTRY": DEFAULT_CLAIM_REGISTRY,
    "PREVIEW_FILES": PREVIEW_FILES,
    "_prior_gate": _matrix_prior_gate,
    "describe": _matrix_describe,
    "observation_template": _matrix_observation_template,
}


@contextmanager
def _bound_engine() -> Iterator[None]:
    with _ENGINE_LOCK:
        previous = {name: getattr(engine, name) for name in _ENGINE_BINDINGS}
        for name, value in _ENGINE_BINDINGS.items():
            setattr(engine, name, value)
        try:
            yield
        finally:
            for name, value in previous.items():
                setattr(engine, name, value)


def _exact_release_gate(context: ReleaseContext) -> None:
    if not all(
        (
            EXPECTED_RELEASE_FILE_SHA256,
            EXPECTED_RELEASE_CANONICAL_SHA256,
            EXPECTED_FIRMWARE_BINARY_SHA256,
            EXPECTED_FIRMWARE_ELF_SHA256,
        )
    ):
        raise OtpTransitionMatrixPhysicalError(
            "physical runner is hard-blocked until the clean build release hashes are frozen"
        )
    try:
        checked = campaign.validate_materialized_release(context.release_file)
    except campaign.OtpTransitionMatrixCampaignError as error:
        raise OtpTransitionMatrixPhysicalError(
            f"OTP transition-matrix release validation failed: {error}"
        ) from error
    compiled = context.release_root.get("compiled_campaign", {})
    anchor = context.release_root.get("predecessor_binding", {})
    expected_action_ids = {item["hardware_action_id"] for item in contract.DESCRIPTORS}
    old_action_ids = {item["hardware_action_id"] for item in old_contract.DESCRIPTORS}
    if (
        checked.get("file_sha256") != EXPECTED_RELEASE_FILE_SHA256
        or checked.get("canonical_sha256") != EXPECTED_RELEASE_CANONICAL_SHA256
        or checked.get("firmware_binary_sha256") != EXPECTED_FIRMWARE_BINARY_SHA256
        or checked.get("firmware_elf_sha256") != EXPECTED_FIRMWARE_ELF_SHA256
        or context.release_file_sha256 != EXPECTED_RELEASE_FILE_SHA256
        or context.release_canonical_sha256 != EXPECTED_RELEASE_CANONICAL_SHA256
        or compiled.get("file_sha256") != EXPECTED_CAMPAIGN_FILE_SHA256
        or compiled.get("canonical_sha256") != EXPECTED_CAMPAIGN_CANONICAL_SHA256
        or anchor.get("result", {}).get("file_sha256") != EXPECTED_ANCHOR_RESULT_SHA256
        or anchor.get("observation", {}).get("file_sha256")
        != EXPECTED_ANCHOR_OBSERVATION_SHA256
        or anchor.get("claim", {}).get("file_sha256") != EXPECTED_ANCHOR_CLAIM_SHA256
        or context.release_root.get("execution_eligible") is not True
        or {str(item["action_id"]) for item in context.actions} != expected_action_ids
        or expected_action_ids & old_action_ids
        or contract.NVS_NAMESPACE == old_contract.NVS_NAMESPACE
        or contract.NVS_KEY == old_contract.NVS_KEY
    ):
        raise OtpTransitionMatrixPhysicalError(
            "exact OTP transition-matrix release gate differs"
        )


def load_release(release_file: Path) -> ReleaseContext:
    with _bound_engine():
        context = engine.load_release(release_file)
    _exact_release_gate(context)
    return context


def required_authorization(context: ReleaseContext, ordinal: int) -> str:
    _exact_release_gate(context)
    return campaign.required_authorization(context.actions[ordinal - 1])


def describe(context: ReleaseContext, ordinal: int) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return deepcopy(_matrix_describe(context, ordinal))


def observation_template(context: ReleaseContext, ordinal: int) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return deepcopy(_matrix_observation_template(context, ordinal))


def preflight(
    context: ReleaseContext, base_url: str, ordinal: int, **kwargs: Any
) -> Preflight:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.preflight(context, base_url, ordinal, **kwargs)


def diagnose_j2_off(
    context: ReleaseContext,
    base_url: str,
    *,
    evidence_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    **kwargs: Any,
) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.diagnose_j2_off(
            context,
            base_url,
            evidence_file=evidence_file,
            claim_registry=claim_registry,
            **kwargs,
        )


def validate_j2_off_diagnostic(
    context: ReleaseContext,
    evidence_file: Path,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.validate_j2_off_diagnostic(
            context, evidence_file, claim_registry=claim_registry
        )


def run_once(
    context: ReleaseContext,
    base_url: str,
    ordinal: int,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    **kwargs: Any,
) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.run_once(
            context,
            base_url,
            ordinal,
            claim_registry=claim_registry,
            **kwargs,
        )


def validate_result(
    context: ReleaseContext,
    result_file: Path,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.validate_result(
            context, result_file, claim_registry=claim_registry
        )


def reconcile_result(
    context: ReleaseContext,
    base_url: str,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    **kwargs: Any,
) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.reconcile_result(
            context,
            base_url,
            claim_registry=claim_registry,
            **kwargs,
        )


def validate_reconciliation(
    context: ReleaseContext,
    reconciliation_file: Path,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.validate_reconciliation(
            context,
            reconciliation_file,
            claim_registry=claim_registry,
        )


def finalize_observation(
    context: ReleaseContext,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    **kwargs: Any,
) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.seal_observation(context, claim_registry=claim_registry, **kwargs)


seal_observation = finalize_observation


def validate_observation(
    context: ReleaseContext,
    observation_file: Path,
    *,
    result_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.validate_observation(
            context,
            observation_file,
            result_file=result_file,
            claim_registry=claim_registry,
        )


def _parse_args(argv: Sequence[str] | None) -> Any:
    with _bound_engine():
        return engine.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        context = load_release(args.release)
        if args.command == "describe":
            output = describe(context, args.ordinal)
        elif args.command == "observation-template":
            output = observation_template(context, args.ordinal)
        elif args.command == "preflight":
            output = preflight(context, args.base_url, args.ordinal).as_dict()
        elif args.command == "diagnose-j2-off":
            output = diagnose_j2_off(
                context,
                args.base_url,
                evidence_file=args.evidence,
                claim_registry=args.claim_registry,
                confirm_j2_off=args.confirm_j2_off,
            )
        elif args.command == "validate-j2-off":
            output = validate_j2_off_diagnostic(
                context,
                args.evidence,
                claim_registry=args.claim_registry,
            )
        elif args.command == "run":
            output = run_once(
                context,
                args.base_url,
                args.ordinal,
                authorization=args.authorize,
                result_file=args.result,
                claim_registry=args.claim_registry,
                prior_result_file=args.prior_result,
                prior_observation_file=args.prior_observation,
                j2_off_diagnostic_file=args.j2_off_diagnostic,
                confirm_no_intervening_visible_refresh=(
                    args.confirm_no_intervening_visible_refresh
                ),
                confirm_j2_on=args.confirm_j2_on,
                confirm_electrical_normal=args.confirm_electrical_normal,
                temperature_c=args.temperature_c,
                poll_count=args.poll_count,
                poll_interval_seconds=args.poll_interval_seconds,
            )
        elif args.command == "validate-result":
            output = validate_result(
                context, args.result, claim_registry=args.claim_registry
            )
        elif args.command == "reconcile-result":
            output = reconcile_result(
                context,
                args.base_url,
                source_result_file=args.source_result,
                result_file=args.result,
                reconciliation_file=args.reconciliation,
                claim_registry=args.claim_registry,
                timeout=args.timeout,
            )
        elif args.command == "validate-reconciliation":
            output = validate_reconciliation(
                context,
                args.reconciliation,
                claim_registry=args.claim_registry,
            )
        elif args.command == "validate-observation":
            output = validate_observation(
                context,
                args.observation,
                result_file=args.result,
                claim_registry=args.claim_registry,
            )
        else:
            output = finalize_observation(
                context,
                result_file=args.result,
                observation_file=args.observation,
                claim_registry=args.claim_registry,
                operator_report=args.operator_report,
                temperature_c=args.temperature_c,
                confirm_reference_preview_checked=(
                    args.confirm_reference_preview_checked
                ),
                confirm_display_matches_reference=(
                    args.confirm_display_matches_reference
                ),
                confirm_no_unexpected_residual=args.confirm_no_unexpected_residual,
                confirm_electrical_normal=args.confirm_electrical_normal,
                confirm_esp32_no_restart=args.confirm_esp32_no_restart,
                confirm_clean_white=args.confirm_clean_white,
                confirm_map_fidelity=args.confirm_map_fidelity,
            )
    except OtpTransitionMatrixPhysicalError as error:
        print(f"EC5 OTP transition-matrix error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
