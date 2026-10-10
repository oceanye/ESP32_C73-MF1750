#!/usr/bin/env python3
"""Materialize, serve, finalize, and replay one production-physical N6 action.

This is the only operator CLI for N6 physical execution.  Live decisions use
the process wall clock; the parser intentionally exposes no evaluated,
claimed, completed, materialized, or finalized timestamp override.  The live
claim is always rooted at this repository, precedes device I/O, and is followed
by at most one POST with no retry or recovery.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.server import ApplicationHttpServer, ApplicationRuntime  # noqa: E402
from host.application import (  # noqa: E402
    AtomicN6ClaimStore,
    N6HttpRefreshDriver,
    N6N5PhysicalPaletteEvidence,
    N6PhysicalBrowserController,
    N6PhysicalExecutionError,
    N6PhysicalPostClaimUnknown,
    N6PhysicalReceiptPaths,
    N6PhysicalReceiptStore,
    N6PhysicalSources,
    N6ProductionProfileFiles,
    N6RuntimeEvidenceFiles,
    N6StaticEvidenceFiles,
    OfflineAdapter,
    compile_n6_physical_context,
    finalize_n6_physical_manual_observation,
    finalize_n6_physical_unknown,
    materialize_n6_physical_manifest,
    measured_gamut_profile_from_n6_manifest,
    measured_palette_from_n6_manifest,
    required_n6_action_authorization,
    required_n6_panel_plan_confirmation,
    required_n6_profile_confirmation,
    validate_n6_physical_finalized_bundle,
    validate_n6_physical_manifest,
    validate_n6_physical_postclaim_incident,
    validate_n6_physical_receipt,
    validate_n6_physical_receipt_durable_commit,
)
from host.application.durable_io import (  # noqa: E402
    DurableWriteError,
    DurableWriteOutcomeUnknown,
    write_new_bytes_durable,
)
from host.application.n6_visible_execution import (  # noqa: E402
    MANUAL_OBSERVATION_KIND,
    N6ClaimConsumed,
    N6VisibleExecutionError,
    seal_n6_manual_observation,
    validate_n6_manual_observation,
)
from host.visible_refresh_campaign import (  # noqa: E402
    ResultState,
    canonical_json_bytes,
    read_local_regular_file,
    result_file_sha256,
)
from tools import mf1750_n5_physical_execution as n5_physical  # noqa: E402


SCHEMA_VERSION = 1
SERVE_CONFIRMATION = (
    "SERVE_ONE_N6_PHYSICAL_ACTION__CLAIM_BEFORE_NETWORK__NO_RETRY_NO_RECOVERY"
)
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_EVIDENCE_BYTES = 8 * 1024 * 1024


class N6PhysicalOnceToolError(ValueError):
    """The physical CLI failed closed before a claim or durable commit."""


class N6PhysicalOncePostClaimUnknown(N6PhysicalOnceToolError):
    """A claim was consumed and the action must never be rerun."""

    def __init__(
        self,
        detail: str,
        *,
        receipt: Mapping[str, Any],
        incident: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.receipt = json.loads(canonical_json_bytes(receipt).decode("utf-8"))
        self.incident = (
            None
            if incident is None
            else json.loads(canonical_json_bytes(incident).decode("utf-8"))
        )


def _wall_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _strict_json_file(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        snapshot = read_local_regular_file(
            path, label=label, maximum_bytes=MAX_JSON_BYTES
        )
    except Exception as error:
        raise N6PhysicalOnceToolError(f"cannot read {label}: {error}") from error

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise N6PhysicalOnceToolError(
                    f"{label} contains duplicate key {key!r}"
                )
            output[key] = value
        return output

    try:
        value = json.loads(
            snapshot.payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                N6PhysicalOnceToolError(
                    f"{label} contains unsupported constant {token}"
                )
            ),
        )
    except N6PhysicalOnceToolError:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        raise N6PhysicalOnceToolError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise N6PhysicalOnceToolError(f"{label} must contain a JSON object")
    if snapshot.payload != canonical_json_bytes(value):
        raise N6PhysicalOnceToolError(
            f"{label} must be stored as exact canonical JSON bytes"
        )
    return value


def _read_bytes(path: Path, *, label: str, maximum_bytes: int) -> bytes:
    try:
        return read_local_regular_file(
            path, label=label, maximum_bytes=maximum_bytes
        ).payload
    except Exception as error:
        raise N6PhysicalOnceToolError(f"cannot read {label}: {error}") from error


def _new_output_path(path: Path, *, label: str) -> Path:
    if not isinstance(path, Path) or not path.name:
        raise N6PhysicalOnceToolError(f"{label} must be an explicit file path")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise N6PhysicalOnceToolError(
            f"{label} parent directory does not exist: {error}"
        ) from error
    if not parent.is_dir():
        raise N6PhysicalOnceToolError(f"{label} parent must be a directory")
    destination = parent / path.name
    if destination.exists() or destination.is_symlink():
        raise N6PhysicalOnceToolError(f"{label} already exists; refusing overwrite")
    return destination


def _write_durable_new_json(
    path: Path, value: Mapping[str, Any], *, label: str
) -> str:
    destination = _new_output_path(path, label=label)
    try:
        return write_new_bytes_durable(destination, canonical_json_bytes(value))
    except DurableWriteOutcomeUnknown:
        raise
    except DurableWriteError as error:
        raise N6PhysicalOnceToolError(f"cannot commit {label}: {error}") from error


def _load_deep_inputs(
    args: argparse.Namespace,
) -> tuple[
    N6PhysicalSources,
    N6ProductionProfileFiles,
    N6StaticEvidenceFiles,
    Mapping[str, Any],
    Mapping[str, Any],
]:
    n5_context = n5_physical.load_n5_physical_context(
        plan_file=args.n5_physical_plan,
        compile_profile_file=args.n5_compile_profile,
        source_manifest_file=args.n5_source_manifest,
        physical_anchor_campaign_file=args.n5_physical_anchor,
        firmware_binary_file=args.n5_firmware_binary,
        science_review_evidence_file=args.n5_science_review_evidence,
        science_review_approval_file=args.n5_science_review_approval,
        science_reviewer_key_file=args.n5_science_reviewer_key,
        namespace=args.n5_namespace,
        minimum_interval_seconds=args.n5_minimum_interval_seconds,
        planned_cooldown_seconds=args.n5_planned_cooldown_seconds,
    )
    observations = tuple(
        _strict_json_file(path, label=f"N5 physical palette observation {index}")
        for index, path in enumerate(args.n5_palette_observation)
    )
    standard_table = _strict_json_file(
        args.n5_standard_table, label="N5 authoritative standard table"
    )
    instrument = _strict_json_file(
        args.n5_instrument_qualification,
        label="N5 instrument qualification",
    )
    finalized_bundle = _strict_json_file(
        args.n5_finalized_bundle, label="N5 physical finalized bundle"
    )
    palette_aggregate = _strict_json_file(
        args.palette_aggregate, label="N5 physical palette aggregate envelope"
    )
    prior = _strict_json_file(args.prior_result, label="N6 prior result")
    sources = N6PhysicalSources(
        offline_manifest=_strict_json_file(
            args.offline_manifest, label="N6 offline manifest"
        ),
        physical_anchor_campaign=_strict_json_file(
            args.physical_anchor, label="N6 physical anchor campaign"
        ),
        physical_anchor_campaign_file=args.physical_anchor,
        binding_review_bytes=_read_bytes(
            args.binding_review_evidence,
            label="N6 physical binding review evidence",
            maximum_bytes=MAX_EVIDENCE_BYTES,
        ),
        minimum_interval_seconds=args.minimum_interval_seconds,
        planned_cooldown_seconds=args.planned_cooldown_seconds,
        palette_aggregate=palette_aggregate,
        palette_aggregate_file=args.palette_aggregate,
        n5_physical_palette=N6N5PhysicalPaletteEvidence(
            context=n5_context,
            observations=observations,
            observation_files=tuple(args.n5_palette_observation),
            standard_table=standard_table,
            standard_table_file=args.n5_standard_table,
            instrument_qualification=instrument,
            instrument_qualification_file=args.n5_instrument_qualification,
            finalized_bundle=finalized_bundle,
            finalized_bundle_file=args.n5_finalized_bundle,
            result_dirs=tuple(args.n5_result_dir),
            profile_reviewer_key_file=args.n5_profile_reviewer_key,
        ),
        gamut_profile=_strict_json_file(
            args.gamut_profile, label="N6 measured gamut profile"
        ),
        prior_result=prior,
        prior_result_sha256=result_file_sha256(prior),
    )
    production_files = N6ProductionProfileFiles(
        profile_file=args.profile,
        campaign_file=args.physical_campaign,
        firmware_binary_file=args.firmware_binary,
        limit_authority_file=args.limit_authority,
        usage_evidence_file=args.usage_evidence,
        review_artifact_file=args.profile_review,
        reviewer_key_file=args.profile_reviewer_key,
    )
    static_files = N6StaticEvidenceFiles(
        formal_review_evidence_file=args.formal_review_evidence,
        runtime_review_evidence_file=args.runtime_review_evidence,
        trusted_reviewer_key_file=args.trusted_reviewer_key,
    )
    formal_envelope = _strict_json_file(
        args.formal_review_envelope, label="N6 authenticated formal review"
    )
    runtime_review_envelope = _strict_json_file(
        args.runtime_review_envelope, label="N6 authenticated runtime review"
    )
    return (
        sources,
        production_files,
        static_files,
        formal_envelope,
        runtime_review_envelope,
    )


def _load_runtime_inputs(
    args: argparse.Namespace,
) -> tuple[Mapping[str, Any], Mapping[str, Any], N6RuntimeEvidenceFiles]:
    authorization = _strict_json_file(
        args.authorization_envelope,
        label="N6 authenticated external authorization",
    )
    observation = _strict_json_file(
        args.runtime_observation_envelope,
        label="N6 authenticated runtime observation",
    )
    files = N6RuntimeEvidenceFiles(
        authorization_evidence_file=args.authorization_evidence,
        runtime_observation_evidence_file=args.runtime_observation_evidence,
        trusted_reviewer_key_file=args.runtime_trusted_reviewer_key,
    )
    return authorization, observation, files


def _load_physical_manifest(
    args: argparse.Namespace,
    *,
    evaluated_at: str,
) -> tuple[
    Mapping[str, Any],
    N6PhysicalSources,
    N6ProductionProfileFiles,
    N6StaticEvidenceFiles,
]:
    sources, production_files, static_files, _formal, _runtime = (
        _load_deep_inputs(args)
    )
    manifest = _strict_json_file(args.manifest, label="N6 physical manifest")
    validate_n6_physical_manifest(
        manifest,
        sources=sources,
        production_files=production_files,
        static_evidence_files=static_files,
        evaluated_at=evaluated_at,
    )
    return manifest, sources, production_files, static_files


def describe_command(args: argparse.Namespace) -> Mapping[str, Any]:
    now = _wall_now()
    sources, production_files, static_files, formal, runtime = _load_deep_inputs(
        args
    )
    context = compile_n6_physical_context(sources)
    manifest = materialize_n6_physical_manifest(
        context,
        sources=sources,
        production_files=production_files,
        static_evidence_files=static_files,
        formal_review_envelope=formal,
        runtime_review_envelope=runtime,
        materialized_at=now,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-n6-physical-describe-result",
        "evaluated_at_from_actual_wall_clock": now,
        "materialization_ready": True,
        "physical_context_canonical_sha256": context["integrity"][
            "canonical_sha256"
        ],
        "prospective_manifest_canonical_sha256": manifest["integrity"][
            "canonical_sha256"
        ],
        "required_tokens": {
            "action": required_n6_action_authorization(manifest),
            "panel_plan": required_n6_panel_plan_confirmation(manifest),
            "profile": required_n6_profile_confirmation(manifest),
        },
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "hardware_qualification_claimed": False,
    }


def materialize_command(args: argparse.Namespace) -> Mapping[str, Any]:
    destination = _new_output_path(args.output, label="N6 physical manifest output")
    now = _wall_now()
    sources, production_files, static_files, formal, runtime = _load_deep_inputs(
        args
    )
    context = compile_n6_physical_context(sources)
    manifest = materialize_n6_physical_manifest(
        context,
        sources=sources,
        production_files=production_files,
        static_evidence_files=static_files,
        formal_review_envelope=formal,
        runtime_review_envelope=runtime,
        materialized_at=now,
    )
    file_sha = _write_durable_new_json(
        destination, manifest, label="N6 physical manifest output"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-n6-physical-materialize-result",
        "materialized_at_from_actual_wall_clock": now,
        "physical_manifest_canonical_sha256": manifest["integrity"][
            "canonical_sha256"
        ],
        "physical_manifest_file_sha256": file_sha,
        "output": str(destination),
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "hardware_qualification_claimed": False,
    }


def _claim_path(manifest: Mapping[str, Any]) -> Path:
    declaration = manifest["legacy_formal_manifest"]["action"]["claim"]
    registry = (
        REPO_ROOT / declaration["workspace_relative_registry"]
    ).resolve(strict=False)
    try:
        registry.relative_to(REPO_ROOT)
    except ValueError as error:
        raise N6PhysicalOnceToolError(
            "N6 physical claim registry escapes repository root"
        ) from error
    destination = registry / declaration["filename"]
    try:
        destination.relative_to(registry)
    except ValueError as error:
        raise N6PhysicalOnceToolError(
            "N6 physical claim filename escapes its registry"
        ) from error
    return destination


def _validate_disk_claim(
    manifest: Mapping[str, Any], receipt: Mapping[str, Any]
) -> Path:
    claim_path = _claim_path(manifest)
    legacy_receipt = receipt["legacy_protocol_receipt"]
    try:
        payload = read_local_regular_file(
            claim_path,
            label="workspace-global N6 physical claim",
            maximum_bytes=MAX_EVIDENCE_BYTES,
        ).payload
    except Exception as error:
        raise N6PhysicalOnceToolError(
            f"cannot read workspace-global N6 physical claim: {error}"
        ) from error
    expected = canonical_json_bytes(legacy_receipt["claim"]) + b"\n"
    if (
        payload != expected
        or hashlib.sha256(payload).hexdigest()
        != legacy_receipt["claim_file_sha256"]
    ):
        raise N6PhysicalOnceToolError(
            "workspace-global N6 physical claim bytes differ from receipt"
        )
    return claim_path


def _incident_path(manifest: Mapping[str, Any]) -> Path:
    claim = _claim_path(manifest)
    return claim.parent / f"{claim.name}.N6-PHYSICAL-UNKNOWN.json"


def serve_command(args: argparse.Namespace) -> Mapping[str, Any]:
    if args.confirm_serve != SERVE_CONFIRMATION:
        raise N6PhysicalOnceToolError(
            f"serve requires --confirm-serve {SERVE_CONFIRMATION!r}"
        )
    try:
        address = ipaddress.ip_address(args.bind)
    except ValueError as error:
        raise N6PhysicalOnceToolError(
            "--bind must be a numeric loopback address"
        ) from error
    if not address.is_loopback:
        raise N6PhysicalOnceToolError("--bind must be a numeric loopback address")
    if not 1 <= args.port <= 65535:
        raise N6PhysicalOnceToolError("--port must be in [1, 65535]")
    receipt_output = _new_output_path(
        args.receipt_output, label="N6 physical receipt output"
    )
    receipt_commit_output = _new_output_path(
        args.receipt_commit_output,
        label="N6 physical receipt durable commit output",
    )
    now = _wall_now()
    manifest, sources, production_files, static_files = _load_physical_manifest(
        args, evaluated_at=now
    )
    authorization, runtime_observation, runtime_files = _load_runtime_inputs(args)
    claim_path = _claim_path(manifest)
    if claim_path.exists() or claim_path.is_symlink():
        raise N6ClaimConsumed(
            "this exact N6 physical action claim is consumed; do not rerun"
        )
    claim_store = AtomicN6ClaimStore(REPO_ROOT)
    claim_store.prepare_registry(manifest["legacy_formal_manifest"])
    receipt_paths = N6PhysicalReceiptPaths(
        receipt_output=receipt_output,
        receipt_commit_output=receipt_commit_output,
        incident_output=_incident_path(manifest),
    )
    if (
        receipt_paths.incident_output.exists()
        or receipt_paths.incident_output.is_symlink()
    ):
        try:
            prior_incident = validate_n6_physical_postclaim_incident(
                _strict_json_file(
                    receipt_paths.incident_output,
                    label="prior N6 physical post-claim UNKNOWN incident",
                ),
                manifest=manifest,
                sources=sources,
                production_files=production_files,
                static_evidence_files=static_files,
                receipt_paths=receipt_paths,
                claim_store=claim_store,
            )
        except BaseException as error:
            raise N6PhysicalOncePostClaimUnknown(
                "fixed per-claim UNKNOWN marker exists but cannot be deeply replayed; do not retry",
                receipt={
                    "physical_manifest_canonical_sha256": manifest["integrity"][
                        "canonical_sha256"
                    ],
                    "attempt_id": args.attempt_id,
                    "incident_path": str(receipt_paths.incident_output),
                },
            ) from error
        raise N6PhysicalOncePostClaimUnknown(
            "this action already has a durable terminal UNKNOWN incident; do not retry",
            receipt=prior_incident["evidence"],
            incident=prior_incident,
        )
    sink = N6PhysicalReceiptStore(
        manifest,
        paths=receipt_paths,
    )
    controller = N6PhysicalBrowserController(
        manifest,
        sources=sources,
        production_files=production_files,
        static_evidence_files=static_files,
        authorization_envelope=authorization,
        runtime_observation_envelope=runtime_observation,
        runtime_evidence_files=runtime_files,
        claim_store=claim_store,
        protocol_driver=N6HttpRefreshDriver(args.device_url),
        attempt_id=args.attempt_id,
        post_claim_receipt_sink=sink,
    )
    legacy_manifest = manifest["legacy_formal_manifest"]
    runtime = ApplicationRuntime(
        measured_palette_from_n6_manifest(legacy_manifest),
        OfflineAdapter(),
        gamut_profiles=(measured_gamut_profile_from_n6_manifest(legacy_manifest),),
        n6_formal_controller=controller,
    )
    server = ApplicationHttpServer((args.bind, args.port), runtime)
    server.daemon_threads = False
    server.block_on_close = True
    server.timeout = 0.25
    print(f"MF-1750 N6 physical UI: {server.origin}/#token={server.security_token}")
    print("Three exact UI tokens are required; claim precedes all device network I/O.")
    print("After claim: at most one POST, synchronous durable receipt, no retry/recovery.")
    try:
        while True:
            server.handle_request()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    receipt = controller.receipt
    if receipt is None:
        incident = sink.incident
        if incident is not None:
            raise N6PhysicalOncePostClaimUnknown(
                "claim consumed; durable emergency UNKNOWN incident was committed",
                receipt=incident["evidence"],
                incident=incident,
            )
        if claim_path.exists() or claim_path.is_symlink():
            raise N6PhysicalOncePostClaimUnknown(
                "workspace-global claim exists but no durable receipt/incident is available; do not retry",
                receipt={
                    "physical_manifest_canonical_sha256": manifest["integrity"][
                        "canonical_sha256"
                    ],
                    "attempt_id": args.attempt_id,
                    "claim_path": str(claim_path),
                },
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "mf1750-n6-physical-serve-result",
            "state": "NO_ACTION_EXECUTED",
            "claim_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
            "hardware_qualification_claimed": False,
        }
    durable_commit = controller.receipt_durable_commit
    if durable_commit is None:
        raise N6PhysicalOncePostClaimUnknown(
            "claim consumed but synchronous durable receipt commit is absent; do not retry",
            receipt=receipt,
        )
    stored_commit = _strict_json_file(
        receipt_commit_output,
        label="stored N6 physical receipt durable commit",
    )
    if stored_commit != durable_commit:
        raise N6PhysicalOncePostClaimUnknown(
            "claim consumed but durable receipt commit file changed; do not retry",
            receipt=receipt,
        )
    validate_n6_physical_receipt_durable_commit(
        stored_commit,
        receipt=receipt,
        paths=receipt_paths,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-n6-physical-serve-result",
        "state": receipt["legacy_protocol_receipt"]["state"],
        "physical_receipt_canonical_sha256": receipt["integrity"][
            "canonical_sha256"
        ],
        "receipt_output": str(receipt_output),
        "receipt_commit_output": str(receipt_commit_output),
        "frame_post_request_count": receipt["classification"][
            "frame_post_request_count"
        ],
        "retry_allowed": False,
        "recovery_allowed": False,
        "hardware_qualification_claimed": False,
    }


def finalize_command(args: argparse.Namespace) -> Mapping[str, Any]:
    output = _new_output_path(args.output, label="N6 physical finalized output")
    manifest_value = _strict_json_file(args.manifest, label="N6 physical manifest")
    historical_time = str(manifest_value.get("materialized_at"))
    manifest, sources, production_files, static_files = _load_physical_manifest(
        args, evaluated_at=historical_time
    )
    _authorization, _runtime, runtime_files = _load_runtime_inputs(args)
    receipt = validate_n6_physical_receipt(
        _strict_json_file(args.receipt, label="N6 physical receipt"),
        manifest=manifest,
        sources=sources,
        production_files=production_files,
        static_evidence_files=static_files,
        runtime_evidence_files=runtime_files,
    )
    receipt_paths = N6PhysicalReceiptPaths(
        receipt_output=args.receipt,
        receipt_commit_output=args.receipt_commit,
        incident_output=_incident_path(manifest),
    )
    receipt_commit = validate_n6_physical_receipt_durable_commit(
        _strict_json_file(
            args.receipt_commit,
            label="N6 physical receipt durable commit",
        ),
        receipt=receipt,
        paths=receipt_paths,
    )
    claim_store = AtomicN6ClaimStore(REPO_ROOT)
    _validate_disk_claim(manifest, receipt)
    finalized_at = _wall_now()
    state = receipt["legacy_protocol_receipt"]["state"]
    if state == ResultState.UNKNOWN_DO_NOT_RETRY.value:
        if args.observation is not None:
            raise N6PhysicalOnceToolError(
                "UNKNOWN physical receipt cannot accept manual promotion"
            )
        bundle = finalize_n6_physical_unknown(
            manifest,
            receipt,
            receipt_durable_commit=receipt_commit,
            receipt_paths=receipt_paths,
            claim_store=claim_store,
            finalized_at=finalized_at,
        )
    else:
        if args.observation is None:
            raise N6PhysicalOnceToolError(
                "protocol-verified physical receipt requires --observation"
            )
        raw_observation = _strict_json_file(
            args.observation, label="N6 manual observation"
        )
        legacy_manifest = manifest["legacy_formal_manifest"]
        legacy_receipt = receipt["legacy_protocol_receipt"]
        if "integrity" in raw_observation:
            observation = validate_n6_manual_observation(
                raw_observation,
                manifest=legacy_manifest,
                protocol_receipt=legacy_receipt,
            )
        else:
            fields = {
                "observed_at",
                "observer_id",
                "full_panel_visual_matches_preview",
                "map_fidelity_pass",
                "orientation_seam_and_ghosting_normal",
                "supply_cv_current_normal",
                "post_refresh_current_normal",
                "temperature_normal",
                "esp32_unexpected_restart",
                "j2_state_after_observation",
                "manual_evidence_sha256",
                "notes",
            }
            if set(raw_observation) != fields:
                raise N6PhysicalOnceToolError(
                    "unsealed manual observation differs from fixed template"
                )
            observation = seal_n6_manual_observation(
                {
                    "schema_version": SCHEMA_VERSION,
                    "kind": MANUAL_OBSERVATION_KIND,
                    "formal_manifest_canonical_sha256": legacy_manifest[
                        "integrity"
                    ]["canonical_sha256"],
                    "protocol_receipt_canonical_sha256": legacy_receipt[
                        "integrity"
                    ]["canonical_sha256"],
                    "action_identity_sha256": legacy_manifest["action"][
                        "action_identity_sha256"
                    ],
                    "attempt_id": receipt["attempt_id"],
                    **raw_observation,
                },
                manifest=legacy_manifest,
                protocol_receipt=legacy_receipt,
            )
        bundle = finalize_n6_physical_manual_observation(
            manifest,
            receipt,
            observation,
            receipt_durable_commit=receipt_commit,
            receipt_paths=receipt_paths,
            claim_store=claim_store,
            finalized_at=finalized_at,
        )
    validate_n6_physical_finalized_bundle(
        bundle,
        manifest=manifest,
        sources=sources,
        production_files=production_files,
        static_evidence_files=static_files,
        runtime_evidence_files=runtime_files,
        receipt_paths=receipt_paths,
        claim_store=claim_store,
    )
    file_sha = _write_durable_new_json(
        output, bundle, label="N6 physical finalized output"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-n6-physical-finalize-result",
        "state": bundle["result"]["state"],
        "finalized_at_from_actual_wall_clock": finalized_at,
        "physical_finalized_canonical_sha256": bundle["integrity"][
            "canonical_sha256"
        ],
        "physical_finalized_file_sha256": file_sha,
        "output": str(output),
        "terminal": True,
        "retry_allowed": False,
        "recovery_allowed": False,
        "hardware_qualification_claimed": False,
    }


def validate_command(args: argparse.Namespace) -> Mapping[str, Any]:
    manifest_input = _strict_json_file(args.manifest, label="N6 physical manifest")
    manifest, sources, production_files, static_files = _load_physical_manifest(
        args, evaluated_at=str(manifest_input.get("materialized_at"))
    )
    output: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-n6-physical-validate-result",
        "physical_manifest_canonical_sha256": manifest["integrity"][
            "canonical_sha256"
        ],
        "valid": True,
        "network_io_performed": False,
        "device_io_performed": False,
        "hardware_qualification_claimed": False,
    }
    if args.incident is not None:
        incident_paths = N6PhysicalReceiptPaths(
            receipt_output=args.incident_receipt_output,
            receipt_commit_output=args.incident_receipt_commit_output,
            incident_output=args.incident,
        )
        incident = validate_n6_physical_postclaim_incident(
            _strict_json_file(
                args.incident, label="N6 physical post-claim UNKNOWN incident"
            ),
            manifest=manifest,
            sources=sources,
            production_files=production_files,
            static_evidence_files=static_files,
            receipt_paths=incident_paths,
            claim_store=AtomicN6ClaimStore(REPO_ROOT),
        )
        output["incident"] = {
            "canonical_sha256": incident["integrity"]["canonical_sha256"],
            "state": ResultState.UNKNOWN_DO_NOT_RETRY.value,
            "terminal": True,
            "finalization_allowed": False,
            "retry_allowed": False,
            "recovery_allowed": False,
            "hardware_qualification_claimed": False,
        }
        return output
    if args.receipt is not None or args.bundle is not None:
        _authorization, _runtime, runtime_files = _load_runtime_inputs(args)
    else:
        runtime_files = None
    if args.receipt is not None:
        assert runtime_files is not None
        receipt = validate_n6_physical_receipt(
            _strict_json_file(args.receipt, label="N6 physical receipt"),
            manifest=manifest,
            sources=sources,
            production_files=production_files,
            static_evidence_files=static_files,
            runtime_evidence_files=runtime_files,
        )
        receipt_paths = N6PhysicalReceiptPaths(
            receipt_output=args.receipt,
            receipt_commit_output=args.receipt_commit,
            incident_output=_incident_path(manifest),
        )
        receipt_commit = validate_n6_physical_receipt_durable_commit(
            _strict_json_file(
                args.receipt_commit,
                label="N6 physical receipt durable commit",
            ),
            receipt=receipt,
            paths=receipt_paths,
        )
        output["receipt"] = {
            "canonical_sha256": receipt["integrity"]["canonical_sha256"],
            "state": receipt["legacy_protocol_receipt"]["state"],
            "workspace_global_claim": str(_validate_disk_claim(manifest, receipt)),
            "durable_commit_canonical_sha256": receipt_commit["integrity"][
                "canonical_sha256"
            ],
        }
    if args.bundle is not None:
        assert runtime_files is not None
        if args.receipt is None:
            raise N6PhysicalOnceToolError(
                "validating a finalized bundle requires its standalone receipt"
            )
        bundle = validate_n6_physical_finalized_bundle(
            _strict_json_file(args.bundle, label="N6 physical finalized bundle"),
            manifest=manifest,
            sources=sources,
            production_files=production_files,
            static_evidence_files=static_files,
            runtime_evidence_files=runtime_files,
            receipt_paths=receipt_paths,
            claim_store=AtomicN6ClaimStore(REPO_ROOT),
        )
        actual_commit = _strict_json_file(
            args.receipt_commit,
            label="N6 physical receipt durable commit",
        )
        if actual_commit != bundle["receipt_durable_commit"]:
            raise N6PhysicalOnceToolError(
                "finalized bundle differs from actual receipt durable commit file"
            )
        claim = _validate_disk_claim(manifest, bundle["physical_receipt"])
        output["bundle"] = {
            "canonical_sha256": bundle["integrity"]["canonical_sha256"],
            "state": bundle["result"]["state"],
            "workspace_global_claim": str(claim),
        }
    return output


def _add_deep_sources(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--offline-manifest", type=Path, required=True)
    parser.add_argument("--physical-anchor", type=Path, required=True)
    parser.add_argument("--binding-review-evidence", type=Path, required=True)
    parser.add_argument("--minimum-interval-seconds", type=float, required=True)
    parser.add_argument("--planned-cooldown-seconds", type=float, required=True)
    parser.add_argument("--palette-aggregate", type=Path, required=True)
    parser.add_argument("--gamut-profile", type=Path, required=True)
    parser.add_argument("--prior-result", type=Path, required=True)

    parser.add_argument("--n5-physical-plan", type=Path, required=True)
    parser.add_argument("--n5-compile-profile", type=Path, required=True)
    parser.add_argument("--n5-source-manifest", type=Path, required=True)
    parser.add_argument("--n5-physical-anchor", type=Path, required=True)
    parser.add_argument("--n5-firmware-binary", type=Path, required=True)
    parser.add_argument("--n5-science-review-evidence", type=Path, required=True)
    parser.add_argument("--n5-science-review-approval", type=Path, required=True)
    parser.add_argument("--n5-science-reviewer-key", type=Path, required=True)
    parser.add_argument("--n5-namespace", required=True)
    parser.add_argument(
        "--n5-minimum-interval-seconds", type=float, required=True
    )
    parser.add_argument(
        "--n5-planned-cooldown-seconds", type=float, required=True
    )
    parser.add_argument("--n5-finalized-bundle", type=Path, required=True)
    parser.add_argument(
        "--n5-result-dir", type=Path, action="append", required=True
    )
    parser.add_argument("--n5-profile-reviewer-key", type=Path, required=True)
    parser.add_argument(
        "--n5-palette-observation", type=Path, action="append", required=True
    )
    parser.add_argument("--n5-standard-table", type=Path, required=True)
    parser.add_argument(
        "--n5-instrument-qualification", type=Path, required=True
    )

    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--physical-campaign", type=Path, required=True)
    parser.add_argument("--firmware-binary", type=Path, required=True)
    parser.add_argument("--limit-authority", type=Path, required=True)
    parser.add_argument("--usage-evidence", type=Path, required=True)
    parser.add_argument("--profile-review", type=Path, required=True)
    parser.add_argument("--profile-reviewer-key", type=Path, required=True)

    parser.add_argument("--formal-review-envelope", type=Path, required=True)
    parser.add_argument("--runtime-review-envelope", type=Path, required=True)
    parser.add_argument("--formal-review-evidence", type=Path, required=True)
    parser.add_argument("--runtime-review-evidence", type=Path, required=True)
    parser.add_argument("--trusted-reviewer-key", type=Path, required=True)


def _add_runtime_sources(parser: argparse.ArgumentParser, *, required: bool) -> None:
    parser.add_argument(
        "--authorization-envelope", type=Path, required=required
    )
    parser.add_argument(
        "--runtime-observation-envelope", type=Path, required=required
    )
    parser.add_argument(
        "--authorization-evidence", type=Path, required=required
    )
    parser.add_argument(
        "--runtime-observation-evidence", type=Path, required=required
    )
    parser.add_argument(
        "--runtime-trusted-reviewer-key", type=Path, required=required
    )


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    describe = subparsers.add_parser(
        "describe", help="deeply describe readiness with zero claim/network/device I/O"
    )
    _add_deep_sources(describe)

    materialize = subparsers.add_parser(
        "materialize", help="durably freeze one physical manifest offline"
    )
    _add_deep_sources(materialize)
    materialize.add_argument("--output", type=Path, required=True)

    serve = subparsers.add_parser(
        "serve", help="serve the loopback physical UI for one claimed action"
    )
    _add_deep_sources(serve)
    _add_runtime_sources(serve, required=True)
    serve.add_argument("--manifest", type=Path, required=True)
    serve.add_argument("--device-url", required=True)
    serve.add_argument("--attempt-id", required=True)
    serve.add_argument("--bind", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--receipt-output", type=Path, required=True)
    serve.add_argument("--receipt-commit-output", type=Path, required=True)
    serve.add_argument("--confirm-serve", required=True)

    finalize = subparsers.add_parser(
        "finalize", help="seal manual PASS/FAIL or terminal UNKNOWN offline"
    )
    _add_deep_sources(finalize)
    _add_runtime_sources(finalize, required=True)
    finalize.add_argument("--manifest", type=Path, required=True)
    finalize.add_argument("--receipt", type=Path, required=True)
    finalize.add_argument("--receipt-commit", type=Path, required=True)
    finalize.add_argument("--observation", type=Path)
    finalize.add_argument("--output", type=Path, required=True)

    validate = subparsers.add_parser(
        "validate", help="deeply replay a manifest and optional receipt/bundle"
    )
    _add_deep_sources(validate)
    _add_runtime_sources(validate, required=False)
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--receipt", type=Path)
    validate.add_argument("--receipt-commit", type=Path)
    validate.add_argument("--bundle", type=Path)
    validate.add_argument("--incident", type=Path)
    validate.add_argument("--incident-receipt-output", type=Path)
    validate.add_argument("--incident-receipt-commit-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "describe":
            output = describe_command(args)
        elif args.command == "materialize":
            output = materialize_command(args)
        elif args.command == "serve":
            output = serve_command(args)
        elif args.command == "finalize":
            output = finalize_command(args)
        else:
            if args.incident is not None:
                if any(
                    value is not None
                    for value in (args.receipt, args.receipt_commit, args.bundle)
                ):
                    raise N6PhysicalOnceToolError(
                        "validate --incident cannot be combined with receipt/commit/bundle"
                    )
                if (
                    args.incident_receipt_output is None
                    or args.incident_receipt_commit_output is None
                ):
                    raise N6PhysicalOnceToolError(
                        "validate --incident requires both expected receipt output paths"
                    )
            elif (
                args.incident_receipt_output is not None
                or args.incident_receipt_commit_output is not None
            ):
                raise N6PhysicalOnceToolError(
                    "incident expected output paths require --incident"
                )
            if args.bundle is not None and args.receipt is None:
                raise N6PhysicalOnceToolError(
                    "validate --bundle requires the standalone --receipt"
                )
            if args.receipt_commit is not None and args.receipt is None:
                raise N6PhysicalOnceToolError(
                    "validate --receipt-commit requires the standalone --receipt"
                )
            if (args.receipt is not None or args.bundle is not None) and (
                args.receipt_commit is None
                or any(
                    getattr(args, name) is None
                    for name in (
                        "authorization_envelope",
                        "runtime_observation_envelope",
                        "authorization_evidence",
                        "runtime_observation_evidence",
                        "runtime_trusted_reviewer_key",
                    )
                )
            ):
                raise N6PhysicalOnceToolError(
                    "validate receipt/bundle requires all runtime evidence arguments"
                )
            output = validate_command(args)
    except (
        N6PhysicalOncePostClaimUnknown,
        N6PhysicalPostClaimUnknown,
        N6ClaimConsumed,
    ) as error:
        print(
            f"N6 physical UNKNOWN_DO_NOT_RETRY: {error}", file=sys.stderr
        )
        return 3
    except (
        N6PhysicalExecutionError,
        N6VisibleExecutionError,
        N6PhysicalOnceToolError,
        DurableWriteError,
        ValueError,
    ) as error:
        print(f"N6 physical error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            output, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        )
    )
    if args.command == "finalize" and output.get("state") == ResultState.FAIL.value:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "N6PhysicalOncePostClaimUnknown",
    "N6PhysicalOnceToolError",
    "SERVE_CONFIRMATION",
    "describe_command",
    "finalize_command",
    "main",
    "materialize_command",
    "parse_args",
    "serve_command",
    "validate_command",
]
