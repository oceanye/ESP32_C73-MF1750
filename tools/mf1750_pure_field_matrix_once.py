#!/usr/bin/env python3
"""Fail-closed one-shot runner for a sealed Stage-III pure-field release.

The tool never flashes firmware or controls the relay.  Every treatment and
factory-OTP white recovery remains a separately diagnosed, claimed, armed and
executed action.  Progression stops for an operator/camera observation after
each treatment and always stops on a suspected new homogeneous colour.
"""

from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_dual_r20_discovery_once as dual  # noqa: E402
from tools import mf1750_ec5_runtime_lut_contract as contract  # noqa: E402
from tools import mf1750_ec5_runtime_lut_physical_once as physical  # noqa: E402
from tools import mf1750_pure_field_matrix_pack as pack  # noqa: E402
from tools import mf1750_reference_535_matrix_pack as reference_pack  # noqa: E402


DEFAULT_RELEASE = Path(
    ".test-output/offline/MF1750_STAGE3_PURE_FIELD_MATRIX_20260822_V5/release.json"
)
NO_NEW = dual.NO_NEW
SUSPECTED_NEW = dual.SUSPECTED_NEW
DECISION_KIND = "mf1750-pure-field-operator-or-camera-decision"
RECONCILIATION_KIND = "mf1750-pure-field-terminal-readback-reconciliation"
INCLUDE_PAIR_SHA256 = dual.INCLUDE_PAIR_SHA256
MONITORS = contract.OPERATOR_MONITORING_CONFIRMATION


class PureFieldError(ValueError):
    """Release, observation, or progression evidence differs."""


def _electrical(header: str) -> Mapping[str, Any]:
    values = {
        "WF20_25": ({"vsh_lv": 6500, "vsl_lv": -8200, "vsh_lv2": 8000, "vsl_lv2": -8800}, 43),
        "WF23_25": ({"vsh_lv": 7200, "vsl_lv": -8400, "vsh_lv2": 8200, "vsl_lv2": -9800}, 43),
        "LEGACY_ACTIVE_535": ({"vsh_lv": 6000, "vsl_lv": -15000, "vsh_lv2": 6200, "vsl_lv2": -6000}, 0),
        "LEGACY_COMMENTED_535": ({"vsh_lv": 6600, "vsl_lv": -15000, "vsh_lv2": 6900, "vsl_lv2": -6200}, 0),
    }
    if header not in values:
        raise PureFieldError("release global header is unknown")
    intermediate, frame_rate = values[header]
    return {
        "gate_positive_mv": 20000,
        "gate_negative_mv": -20000,
        "full_source_positive_mv": 15000,
        "full_source_negative_mv": -15000,
        "intermediate_source_mv": intermediate,
        "frame_rate_hz": frame_rate,
        "vcom_written_or_swept": False,
        "panel_fpl_or_film_lot_qualified": False,
    }


def _image(value: Mapping[str, Any]) -> dual.Image:
    return dual.Image(
        binary=Path(str(value["binary"])),
        elf=Path(str(value["elf"])),
        binary_sha256=str(value["binary_sha256"]),
        elf_sha256=str(value["elf_sha256"]),
        build_tag=str(value["build_tag"]),
        test_id=str(value["test_id"]),
        environment=str(value["environment"]),
        nvs_namespace=str(value["nvs_namespace"]),
        descriptor_id=str(value["descriptor_id"]),
        action_id=str(value["action_id"]),
        role=str(value["role"]),
    )


def _candidates(release: Mapping[str, Any]) -> dict[str, dual.Candidate]:
    result: dict[str, dual.Candidate] = {}
    for item in release["candidates"]:
        candidate = dual.Candidate(
            key=str(item["key"]),
            profile_id=str(item["profile_id"]),
            global_header=str(item["global_header"]),
            campaign_id=str(release["campaign_id"]),
            contract_id=str(item["contract_id"]),
            release_id=str(item["release_id"]),
            treatment=_image(item["treatment"]),
            recovery=_image(item["recovery"]),
            electrical=_electrical(str(item["global_header"])),
        )
        result[candidate.key] = candidate
    if list(result) != release["candidate_order"] or len(result) != release["candidate_count"]:
        raise PureFieldError("release candidate order differs")
    return result


def _release(path: Path) -> tuple[Mapping[str, Any], dict[str, dual.Candidate]]:
    probe = json.loads(path.read_text(encoding="utf-8"))
    if probe.get("kind") == pack.KIND:
        value = pack.validate_release(path)
    elif probe.get("kind") == reference_pack.KIND:
        value = reference_pack.validate_release(path)
    else:
        raise PureFieldError("release kind is not a supported pure-field matrix")
    return value, _candidates(value)


def load_context(
    release: Mapping[str, Any], candidate: dual.Candidate, release_file: Path = DEFAULT_RELEASE
) -> physical.ReleaseContext:
    dual.validate_artifacts(candidate)
    base = physical.load_release(dual.BASE_RELEASE)
    root = copy.deepcopy(base.root)
    root.update(
        {
            "profile_id": candidate.profile_id,
            "campaign_id": candidate.campaign_id,
            "contract_id": candidate.contract_id,
            "release_id": candidate.release_id,
        }
    )
    profile = root["profile_contract"]
    profile.update(
        {
            "profile_id": candidate.profile_id,
            "campaign_id": candidate.campaign_id,
            "contract_id": candidate.contract_id,
            "requested_electrical_metadata": dict(candidate.electrical),
            "vendor_filename_numeric_tokens": (
                [20, 25]
                if candidate.global_header == "WF20_25"
                else (
                    [23, 25]
                    if candidate.global_header == "WF23_25"
                    else [-128, 127]
                )
            ),
            "generated_include": {
                "relative_path": (
                    "src/generated/spd1657_legacy_535_reference.inc"
                    if release.get("kind") == reference_pack.KIND
                    else "WF20+WF23 generated include pair"
                ),
                "sha256": release.get("generated_include_sha256", INCLUDE_PAIR_SHA256),
            },
        }
    )
    images = (candidate.treatment, candidate.recovery)
    frame = release["frame_contract"]
    payloads = (
        {
            "frame_sha256": frame["frame_sha256"],
            "frame_fnv1a": frame["frame_fnv1a"],
            "cs1_dtm_sha256": frame["cs1_dtm_sha256"],
            "cs1_dtm_fnv1a": frame["cs1_dtm_fnv1a"],
            "cs2_dtm_sha256": frame["cs2_dtm_sha256"],
            "cs2_dtm_fnv1a": frame["cs2_dtm_fnv1a"],
        },
        {
            "frame_sha256": "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
            "frame_fnv1a": 0x13340DC5,
            "cs1_dtm_sha256": "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
            "cs1_dtm_fnv1a": 0xB7A855C5,
            "cs2_dtm_sha256": "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
            "cs2_dtm_fnv1a": 0xB7A855C5,
        },
    )
    for ordinal, (image, payload) in enumerate(zip(images, payloads, strict=True), 1):
        action = next(item for item in profile["actions"] if item["ordinal"] == ordinal)
        action.update(
            {
                "profile_id": candidate.profile_id,
                "campaign_id": candidate.campaign_id,
                "environment": image.environment,
                "nvs_namespace": image.nvs_namespace,
                "hardware_action_id": image.action_id,
                "transaction_descriptor_sha256": image.descriptor_id,
                "role": image.role,
                "payload_identity": payload,
            }
        )
        binding = next(
            item for item in root["action_artifact_bindings"] if item["ordinal"] == ordinal
        )
        binding.update(
            {
                "build_tag": image.build_tag,
                "test_id": image.test_id,
                "campaign_id": candidate.campaign_id,
                "environment": image.environment,
                "nvs_namespace": image.nvs_namespace,
                "hardware_action_id": image.action_id,
                "transaction_descriptor_sha256": image.descriptor_id,
                "firmware_binary_sha256": image.binary_sha256,
                "firmware_elf_sha256": image.elf_sha256,
                "frame_fnv1a": payload["frame_fnv1a"],
                "cs1_dtm_fnv1a": payload["cs1_dtm_fnv1a"],
                "cs2_dtm_fnv1a": payload["cs2_dtm_fnv1a"],
                "generated_include_sha256": (
                    release.get("generated_include_sha256", INCLUDE_PAIR_SHA256)
                    if ordinal == 1
                    else None
                ),
                "role": image.role,
            }
        )
        if ordinal == 1:
            # The pure-field firmware intentionally uses a distinct mutation
            # vocabulary from the older empirical-H3 atlas.  Keeping the
            # inherited H3 strings makes ARM fail before any driver call.
            binding.update(
                {
                    "arm_intent": (
                        "ARM_ONE_FIXED_PURE_FIELD_CANDIDATE_NOT_HARDWARE_AUTHORIZATION"
                    ),
                    "execute_intent": "EXECUTE_ONE_FIXED_PURE_FIELD_CANDIDATE_ONCE",
                }
            )
    return physical.ReleaseContext(root=root, release_file=release_file.resolve())


def describe(path: Path = DEFAULT_RELEASE) -> dict[str, Any]:
    release, candidates = _release(path)
    return {
        "schema_version": 1,
        "kind": "mf1750-pure-field-matrix-supervised-plan",
        "candidate_order": list(candidates),
        "treatment_screens": release["treatment_refresh_count"],
        "white_recoveries": release["white_recovery_refresh_count"],
        "maximum_visible_refreshes": release["maximum_planned_refresh_count"],
        "per_screen_waveform_sets": 2,
        "per_screen_endpoint_observations": 16,
        "total_endpoint_observations": release["total_endpoint_observations"],
        "spatial_dithering": False,
        "partial_refresh": False,
        "unknown_commands": False,
        "mid_refresh_power_cut": False,
        "spi_hz": 1_000_000,
        "camera_hook_reserved": True,
        "camera_calibration_complete": False,
        "unattended_autochain_enabled": False,
        "decision_policy": {
            NO_NEW: "independent_white_recovery_then_next_candidate",
            SUSPECTED_NEW: "independent_white_recovery_then_stop_for_replication",
            "striped_or_nonuniform": NO_NEW,
            "brightness_only": NO_NEW,
        },
        "release_canonical_sha256": release["integrity"]["canonical_sha256"],
    }


def _successful_result(path: Path, candidate: dual.Candidate, ordinal: int) -> Mapping[str, Any]:
    return dual._successful_result(path, candidate, ordinal)  # noqa: SLF001


@contextmanager
def _physical_overrides(
    candidate: dual.Candidate, release: Mapping[str, Any]
):
    """Bind the shared physical runner to this matrix candidate's live ABI.

    The original dual-R20 campaign always exposed WF20 on CS1 and WF23 on CS2.
    The reference-first firmware instead exposes the two exact-chip legacy 535-byte
    tables.  Treating those reference labels as the old WF20/WF23 labels would make
    the J2-OFF diagnostic fail before mutation even when the compiled firmware is
    correct.
    """

    original_marker = contract.compiled_descriptor_marker
    original_version = physical._expect_version  # noqa: SLF001
    original_terminal_driver = physical._expect_terminal_driver  # noqa: SLF001
    reference_first = release.get("kind") == reference_pack.KIND
    expected_cs1 = "LEGACY_ACTIVE_535" if reference_first else "WF20_25"
    expected_cs2 = "LEGACY_COMMENTED_535" if reference_first else "WF23_25"

    def marker(profile_id: str, role: str) -> str:
        if profile_id == candidate.profile_id:
            image = candidate.recovery if role == contract.ROLE_WHITE else candidate.treatment
            return dual._marker(candidate, image)  # noqa: SLF001
        return original_marker(profile_id, role)

    def expect_version(
        value: Mapping[str, Any], context: physical.ReleaseContext, ordinal: int
    ) -> None:
        if ordinal == 1:
            profile = value.get("profile")
            if not isinstance(profile, Mapping) or (
                profile.get("compiled_profile_count") != 2
                or profile.get("global_header_profile") != candidate.global_header
                or profile.get("cs1_r20_profile") != expected_cs1
                or profile.get("cs2_r20_profile") != expected_cs2
            ):
                raise physical.PhysicalOnceError("pure-field version mapping differs")
            adjusted = copy.deepcopy(value)
            adjusted["profile"]["compiled_profile_count"] = 1
            original_version(adjusted, context, ordinal)
            return
        original_version(value, context, ordinal)

    def expect_terminal_driver(
        value: Any, context: physical.ReleaseContext, ordinal: int
    ) -> None:
        if ordinal != 1:
            original_terminal_driver(value, context, ordinal)
            return
        binding = context.binding(ordinal)
        payload = context.action(ordinal)["payload_identity"]
        frozen = physical.atlas.FROZEN_IDENTITIES
        adjusted = copy.deepcopy(frozen)
        adjusted["atlas"] = {
            "frame": (payload["frame_sha256"], binding["frame_fnv1a"]),
            "cs1": (payload["cs1_dtm_sha256"], binding["cs1_dtm_fnv1a"]),
            "cs2": (payload["cs2_dtm_sha256"], binding["cs2_dtm_fnv1a"]),
        }
        physical.atlas.FROZEN_IDENTITIES = adjusted
        try:
            original_terminal_driver(value, context, ordinal)
        finally:
            physical.atlas.FROZEN_IDENTITIES = frozen

    contract.compiled_descriptor_marker = marker
    physical._expect_version = expect_version  # noqa: SLF001
    physical._expect_terminal_driver = expect_terminal_driver  # noqa: SLF001
    try:
        yield
    finally:
        contract.compiled_descriptor_marker = original_marker
        physical._expect_version = original_version  # noqa: SLF001
        physical._expect_terminal_driver = original_terminal_driver  # noqa: SLF001


def record_decision(
    candidate: dual.Candidate, treatment_result: Path, outcome: str, notes: str, source: str
) -> dict[str, Any]:
    result = _successful_result(treatment_result, candidate, 1)
    return physical._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": DECISION_KIND,
            "candidate": candidate.key,
            "profile_id": candidate.profile_id,
            "treatment_result_sha256": contract.sha256(treatment_result.read_bytes()),
            "treatment_claim_file_sha256": result["claim_file_sha256"],
            "observation_source": source,
            "outcome": outcome,
            "notes": notes,
            "homogeneous_stable_new_colour_proven": False,
            "next_step": (
                "WHITE_RECOVERY_THEN_NEXT_CANDIDATE"
                if outcome == NO_NEW
                else "WHITE_RECOVERY_THEN_STOP_FOR_REPLICATION"
            ),
            "automatic_next_request_authorized": False,
        }
    )


def _decision(path: Path, candidate: dual.Candidate) -> Mapping[str, Any]:
    value = physical._read_json(path, label="pure-field decision")  # noqa: SLF001
    physical._validate_seal(value, label="pure-field decision")  # noqa: SLF001
    if (
        value.get("kind") != DECISION_KIND
        or value.get("candidate") != candidate.key
        or value.get("profile_id") != candidate.profile_id
        or value.get("outcome") not in (NO_NEW, SUSPECTED_NEW)
        or value.get("automatic_next_request_authorized") is not False
    ):
        raise PureFieldError("pure-field decision differs")
    return value


def _check_progression(
    args: argparse.Namespace, order: list[str], candidates: Mapping[str, dual.Candidate]
) -> None:
    candidate = candidates[args.candidate]
    if args.ordinal == 2:
        if args.decision is None:
            raise PureFieldError("white recovery requires this treatment decision")
        _decision(args.decision, candidate)
    index = order.index(candidate.key)
    if args.ordinal == 1 and index:
        if args.prior_decision is None or args.prior_recovery_result is None:
            raise PureFieldError("next treatment requires prior no-new decision and white result")
        previous = candidates[order[index - 1]]
        decision = _decision(args.prior_decision, previous)
        if decision["outcome"] != NO_NEW:
            raise PureFieldError("suspected new colour blocks the next unswapped candidate")
        _successful_result(args.prior_recovery_result, previous, 2)


def _diagnose(
    args: argparse.Namespace,
    release: Mapping[str, Any],
    candidate: dual.Candidate,
) -> dict[str, Any]:
    context = load_context(release, candidate, args.release)
    requester = physical._http_requester(args.base_url, args.timeout_s)  # noqa: SLF001
    screen = physical.SCREEN_INITIAL if args.ordinal == 1 else physical.SCREEN_RECOVERY
    with _physical_overrides(candidate, release):
        return physical.diagnose_j2_off(
            context,
            args.ordinal,
            operator_temperature_c=args.temperature_c,
            operator_screen_state=screen,
            operator_j2_state="OFF",
            operator_monitoring_state=MONITORS,
            requester=requester,
        )


def _run(
    args: argparse.Namespace,
    release: Mapping[str, Any],
    order: list[str],
    candidates: Mapping[str, dual.Candidate],
) -> dict[str, Any]:
    _check_progression(args, order, candidates)
    candidate = candidates[args.candidate]
    context = load_context(release, candidate, args.release)
    diagnostic = physical._read_json(args.diagnostic, label="J2-OFF diagnostic")  # noqa: SLF001
    requester = physical._http_requester(args.base_url, args.timeout_s)  # noqa: SLF001
    with _physical_overrides(candidate, release):
        authorization = physical.required_authorization(
            context, args.ordinal, args.temperature_c, diagnostic
        )
        return physical.run_once(
            context,
            args.ordinal,
            operator_temperature_c=args.temperature_c,
            operator_j2_state="ON",
            operator_monitoring_state=MONITORS,
            authorization=authorization,
            diagnostic=diagnostic,
            requester=requester,
            claim_registry=args.claim_registry,
            poll_count=args.poll_count,
            poll_interval_seconds=args.poll_interval_seconds,
        )


def _reconcile(
    args: argparse.Namespace,
    release: Mapping[str, Any],
    candidate: dual.Candidate,
) -> dict[str, Any]:
    """Seal a completed action after a host-only terminal evidence mismatch.

    This path is deliberately GET-only and is not a second execution path.  It
    requires the already-consumed permanent claim, the original J2-OFF
    diagnostic, the same boot nonce, and exact terminal device evidence.
    """

    if args.ordinal != 1:
        raise PureFieldError("terminal reconciliation is limited to treatment ordinal1")
    context = load_context(release, candidate, args.release)
    temperature = physical._temperature(args.temperature_c, context, 1)  # noqa: SLF001
    diagnostic = physical._read_json(  # noqa: SLF001
        args.diagnostic, label="J2-OFF diagnostic"
    )
    boot_nonce = physical.validate_diagnostic(
        context, 1, diagnostic, operator_temperature_c=temperature
    )
    authorization = physical.required_authorization(
        context, 1, temperature, diagnostic
    )
    claim_path = physical._claim_path(context, 1, args.claim_registry)  # noqa: SLF001
    claim = physical._read_json(claim_path, label="permanent host claim")  # noqa: SLF001
    physical._validate_seal(claim, label="permanent host claim")  # noqa: SLF001
    expected_claim = {
        "kind": physical.CLAIM_KIND,
        "release_id": context.release_id,
        "profile_id": context.profile_id,
        "ordinal": 1,
        "role": context.action(1)["role"],
        "hardware_action_id": context.action(1)["hardware_action_id"],
        "operator_temperature_c": temperature,
        "authorization_sha256": contract.sha256(authorization.encode("utf-8")),
        "diagnostic_canonical_sha256": diagnostic["integrity"]["canonical_sha256"],
        "state": "permanently_consumed_do_not_retry",
        "created_before_network": True,
    }
    for key, wanted in expected_claim.items():
        if claim.get(key) != wanted:
            raise PureFieldError(f"permanent claim {key} differs")

    requester = physical._http_requester(args.base_url, args.timeout_s)  # noqa: SLF001
    binding = context.binding(1)
    base = str(binding["base_route"])
    headers = physical._headers(  # noqa: SLF001
        context, 1, boot_nonce, intent="READ_ONLY_REPORT"
    )
    status = physical._get(requester, f"{base}/status", headers=headers)  # noqa: SLF001
    report = physical._get(requester, f"{base}/report", headers=headers)  # noqa: SLF001
    physical._expect_identity(status, context, 1, label="terminal status")  # noqa: SLF001
    terminal_status = {
        "boot_nonce": boot_nonce,
        "state": "complete",
        "phase": 0,
        "phase_name": "READY",
        "cursor_raw": 2,
        "next_ordinal": 2,
        "campaign_complete": True,
        "fixture_self_check_passed": True,
        "cursor_valid": True,
        "persistent_key_present": True,
        "execute_pending": False,
        "arm_request_count": 1,
        "execute_request_count": 1,
        "total_driver_call_count": 1,
        "gpio_initialized": True,
        "rst": 0,
        "cs": 0,
        "cs2": 0,
        "sck": 0,
        "dc": 0,
        "mosi": 0,
    }
    for key, wanted in terminal_status.items():
        if status.get(key) != wanted:
            raise PureFieldError(f"terminal status {key} differs")
    if status.get("busy") not in (0, 1):
        raise PureFieldError("terminal status BUSY differs")
    physical._terminal_report(report, context, 1)  # noqa: SLF001

    return physical._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": physical.RESULT_KIND,
            "reconciliation_kind": RECONCILIATION_KIND,
            "release_id": context.release_id,
            "profile_id": context.profile_id,
            "ordinal": 1,
            "role": context.action(1)["role"],
            "hardware_action_id": context.action(1)["hardware_action_id"],
            "operator_temperature_c": temperature,
            "operator_j2_assertion": "ON",
            "reconciliation_operator_j2_assertion": "OFF",
            "j2_is_device_measured": False,
            "operator_monitoring_state": MONITORS,
            "boot_nonce": boot_nonce,
            "claim_file": str(claim_path.resolve()),
            "claim_file_sha256": contract.sha256(claim_path.read_bytes()),
            "preflight_get_requests_after_claim": 4,
            "arm_posts": 1,
            "execute_posts": 1,
            "original_terminal_report_get_requests": 1,
            "reconciliation_get_requests": 2,
            "status_canonical_sha256": contract.sha256(
                contract.canonical_json_bytes(status)
            ),
            "report_canonical_sha256": contract.sha256(
                contract.canonical_json_bytes(report)
            ),
            "visible_refreshes": 1,
            "outcome": "success",
            "retry_allowed": False,
            "automatic_chaining_performed": False,
            "automatic_recovery_performed": False,
            "profile_switch_performed": False,
            "original_host_postcheck_error": (
                "terminal driver input_fnv1a evidence differs"
            ),
            "device_terminal_result": True,
        }
    )


def _common_live(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--ordinal", type=int, choices=(1, 2), required=True)
    parser.add_argument("--temperature-c", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--timeout-s", type=float, default=10.0)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=DEFAULT_RELEASE)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("describe")
    diagnose = commands.add_parser("diagnose")
    _common_live(diagnose)
    diagnose.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    _common_live(run)
    run.add_argument("--diagnostic", type=Path, required=True)
    run.add_argument("--decision", type=Path)
    run.add_argument("--prior-decision", type=Path)
    run.add_argument("--prior-recovery-result", type=Path)
    run.add_argument("--claim-registry", type=Path, required=True)
    run.add_argument("--poll-count", type=int, default=10)
    run.add_argument("--poll-interval-seconds", type=float, default=5.0)
    run.add_argument("--output", type=Path, required=True)
    reconcile = commands.add_parser("reconcile")
    _common_live(reconcile)
    reconcile.add_argument("--diagnostic", type=Path, required=True)
    reconcile.add_argument("--claim-registry", type=Path, required=True)
    reconcile.add_argument("--output", type=Path, required=True)
    record = commands.add_parser("record")
    record.add_argument("--candidate", required=True)
    record.add_argument("--treatment-result", type=Path, required=True)
    record.add_argument("--outcome", choices=(NO_NEW, SUSPECTED_NEW), required=True)
    record.add_argument("--source", choices=("operator", "camera_reviewed"), default="operator")
    record.add_argument("--notes", default="")
    record.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        release, candidates = _release(args.release)
        if args.command == "describe":
            report = describe(args.release)
        elif args.candidate not in candidates:
            raise PureFieldError("candidate is not in the sealed release")
        elif args.command == "record":
            report = record_decision(
                candidates[args.candidate],
                args.treatment_result,
                args.outcome,
                args.notes,
                args.source,
            )
            physical._write_new(args.output, report, label="pure-field decision")  # noqa: SLF001
        elif args.command == "diagnose":
            report = _diagnose(args, release, candidates[args.candidate])
            physical._write_new(args.output, report, label="J2-OFF diagnostic")  # noqa: SLF001
        elif args.command == "reconcile":
            with _physical_overrides(candidates[args.candidate], release):
                report = _reconcile(args, release, candidates[args.candidate])
            physical._write_new(args.output, report, label="reconciled physical result")  # noqa: SLF001
        else:
            report = _run(args, release, list(candidates), candidates)
            physical._write_new(args.output, report, label="physical result")  # noqa: SLF001
    except (
        PureFieldError,
        pack.PackError,
        reference_pack.PackError,
        dual.DualR20Error,
        physical.PhysicalOnceError,
    ) as error:
        print(f"pure-field runner error: {error}")
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
