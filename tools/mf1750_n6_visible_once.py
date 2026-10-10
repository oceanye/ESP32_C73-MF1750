#!/usr/bin/env python3
"""Materialize, serve, finalize, or validate one formal N6 browser action.

``describe`` and ``materialize`` are pure offline operations.  ``serve`` is
the only live entry point: it validates every external input before exposing a
loopback browser UI, and the server-side controller atomically consumes the
workspace-global claim before making any device request.  The browser still
requires its own exact one-shot arm phrase.  There is no retry or recovery
command.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.server import ApplicationHttpServer, ApplicationRuntime  # noqa: E402
from host.application import OfflineAdapter  # noqa: E402
from host.application.n6_visible_execution import (  # noqa: E402
    MANUAL_OBSERVATION_KIND,
    N6_ARM_CONFIRMATION,
    AtomicN6ClaimStore,
    N6BrowserExecutionController,
    N6ClaimConsumed,
    N6HttpRefreshDriver,
    N6PostClaimUnknown,
    N6VisibleExecutionError,
    describe_n6_formal_materialization,
    finalize_n6_manual_observation,
    finalize_n6_unknown_receipt,
    materialize_n6_formal_manifest,
    measured_gamut_profile_from_n6_manifest,
    measured_palette_from_n6_manifest,
    n6_finalized_bundle_file_sha256,
    n6_formal_manifest_file_sha256,
    seal_n6_manual_observation,
    validate_n6_finalized_bundle,
    validate_n6_formal_manifest,
    validate_n6_manual_observation,
    validate_n6_materialization_description,
    validate_n6_protocol_receipt,
)
from host.visible_refresh_campaign import (  # noqa: E402
    ResultState,
    canonical_json_bytes,
    result_file_sha256,
)


class N6VisibleOnceToolError(ValueError):
    """A CLI input or evidence destination failed closed."""


class N6PostClaimEvidenceUnknown(RuntimeError):
    """A permanent claim exists but receipt/finalization durability is unknown."""


LEGACY_LIVE_BLOCK_MESSAGE = (
    "legacy N6 serve is disabled before claim/network: formal/runtime reviews "
    "and the limit profile are self-sealed rather than authenticated against "
    "actual evidence bytes and a trusted reviewer key; use the physical "
    "production browser runner instead"
)


def _strict_json_file(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise N6VisibleOnceToolError(f"cannot read {label}: {error}") from error

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise N6VisibleOnceToolError(
                    f"{label} contains duplicate key {key!r}"
                )
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                N6VisibleOnceToolError(
                    f"{label} contains unsupported constant {token}"
                )
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise N6VisibleOnceToolError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise N6VisibleOnceToolError(f"{label} must contain a JSON object")
    return value


def _new_output_path(path: Path, *, label: str) -> Path:
    if not isinstance(path, Path) or not path.name:
        raise N6VisibleOnceToolError(f"{label} must be an explicit file path")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise N6VisibleOnceToolError(
            f"{label} parent directory does not exist: {error}"
        ) from error
    if not parent.is_dir():
        raise N6VisibleOnceToolError(f"{label} parent must be a directory")
    destination = parent / path.name
    if destination.exists() or destination.is_symlink():
        raise N6VisibleOnceToolError(f"{label} already exists; refusing overwrite")
    return destination


def _write_new_json(path: Path, value: Mapping[str, Any], *, label: str) -> str:
    destination = _new_output_path(path, label=label)
    payload = canonical_json_bytes(value)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(destination, flags, 0o600)
    except FileExistsError as error:
        raise N6VisibleOnceToolError(
            f"{label} already exists; refusing overwrite"
        ) from error
    except OSError as error:
        raise N6VisibleOnceToolError(f"cannot create {label}: {error}") from error
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise N6VisibleOnceToolError(
            f"{label} write outcome is unknown; do not overwrite or retry: {error}"
        ) from error
    return hashlib.sha256(payload).hexdigest()


def _claim_path(manifest: Mapping[str, Any]) -> Path:
    declaration = manifest["action"]["claim"]
    registry = (REPO_ROOT / declaration["workspace_relative_registry"]).resolve(
        strict=False
    )
    try:
        registry.relative_to(REPO_ROOT)
    except ValueError as error:
        raise N6VisibleOnceToolError("N6 claim registry escapes repository root") from error
    path = (registry / declaration["filename"]).resolve(strict=False)
    try:
        path.relative_to(registry)
    except ValueError as error:
        raise N6VisibleOnceToolError("N6 claim filename escapes registry") from error
    return path


def _validate_disk_claim(
    manifest: Mapping[str, Any], receipt: Mapping[str, Any]
) -> Path:
    path = _claim_path(manifest)
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise N6VisibleOnceToolError(
            f"cannot read the workspace-global N6 claim: {error}"
        ) from error
    expected = canonical_json_bytes(receipt["claim"]) + b"\n"
    if payload != expected or hashlib.sha256(payload).hexdigest() != receipt["claim_file_sha256"]:
        raise N6VisibleOnceToolError(
            "workspace-global N6 claim bytes differ from the protocol receipt"
        )
    return path


def _optional_json(path: Optional[Path], *, label: str) -> Mapping[str, Any] | None:
    return None if path is None else _strict_json_file(path, label=label)


def _materialization_inputs(args: argparse.Namespace) -> dict[str, Any]:
    prior = _optional_json(args.prior_result, label="N6 prior result")
    return {
        "palette_aggregate": _optional_json(
            args.palette_aggregate, label="N6 measured palette aggregate"
        ),
        "gamut_profile": _optional_json(
            args.gamut_profile, label="N6 measured gamut profile"
        ),
        "formal_artifact_review": _optional_json(
            args.artifact_review, label="N6 formal artifact review"
        ),
        "reviewed_limit_profile": _optional_json(
            args.limit_profile, label="N6 reviewed limit profile"
        ),
        "runtime_review": _optional_json(
            args.runtime_review, label="N6 runtime review"
        ),
        "prior_result": prior,
        "prior_result_sha256": None if prior is None else result_file_sha256(prior),
    }


def describe_command(args: argparse.Namespace) -> Mapping[str, Any]:
    offline = _strict_json_file(args.offline_manifest, label="N6 offline manifest")
    result = describe_n6_formal_materialization(
        offline,
        evaluated_at=args.evaluated_at,
        **_materialization_inputs(args),
    )
    validate_n6_materialization_description(result)
    return result


def materialize_command(args: argparse.Namespace) -> Mapping[str, Any]:
    offline = _strict_json_file(args.offline_manifest, label="N6 offline manifest")
    inputs = _materialization_inputs(args)
    missing = [name for name, value in inputs.items() if value is None]
    if missing:
        raise N6VisibleOnceToolError(
            "materialize inputs are incomplete: " + ", ".join(missing)
        )
    manifest = materialize_n6_formal_manifest(
        offline,
        materialized_at=args.materialized_at,
        **inputs,
    )
    file_sha256 = _write_new_json(
        args.output, manifest, label="N6 formal manifest output"
    )
    return {
        "kind": "mf1750-n6-materialize-cli-result",
        "formal_manifest_canonical_sha256": manifest["integrity"][
            "canonical_sha256"
        ],
        "formal_manifest_file_sha256": file_sha256,
        "output": str(args.output),
        "hardware_execution_authorized": False,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
    }


def _validated_live_inputs(
    args: argparse.Namespace,
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    manifest = validate_n6_formal_manifest(
        _strict_json_file(args.manifest, label="N6 formal manifest")
    )
    authorization = _strict_json_file(
        args.authorization, label="N6 external one-visible authorization"
    )
    runtime_observation = _strict_json_file(
        args.runtime_observation, label="N6 live runtime observation"
    )
    # The controller constructor and origin binding perform the authorization
    # and runtime deep validation before the UI can be used.
    return manifest, authorization, runtime_observation


def serve_command(args: argparse.Namespace) -> Mapping[str, Any]:
    raise N6VisibleOnceToolError(LEGACY_LIVE_BLOCK_MESSAGE)

    # Retained below as a non-reachable reference implementation until the
    # physical production wrapper has replaced this legacy operator path.
    if args.confirm != N6_ARM_CONFIRMATION:
        raise N6VisibleOnceToolError(
            f"serve requires --confirm {N6_ARM_CONFIRMATION!r}"
        )
    try:
        address = ipaddress.ip_address(args.bind)
    except ValueError as error:
        raise N6VisibleOnceToolError("--bind must be a numeric loopback address") from error
    if not address.is_loopback:
        raise N6VisibleOnceToolError("--bind must be a numeric loopback address")
    if not 1 <= args.port <= 65535:
        raise N6VisibleOnceToolError("--port must be an explicit value in [1, 65535]")
    receipt_destination = _new_output_path(
        args.receipt_output, label="N6 protocol receipt output"
    )
    manifest, authorization, runtime_observation = _validated_live_inputs(args)
    if _claim_path(manifest).exists():
        raise N6ClaimConsumed(
            "this exact N6 action claim already exists in the repository; do not rerun"
        )
    palette = measured_palette_from_n6_manifest(manifest)
    profile = measured_gamut_profile_from_n6_manifest(manifest)
    controller = N6BrowserExecutionController(
        manifest,
        authorization=authorization,
        claim_store=AtomicN6ClaimStore(REPO_ROOT),
        protocol_driver=N6HttpRefreshDriver(args.device_url),
        attempt_id=args.attempt_id,
    )
    runtime = ApplicationRuntime(
        palette,
        OfflineAdapter(),
        gamut_profiles=(profile,),
        n6_formal_controller=controller,
    )
    server = ApplicationHttpServer((args.bind, args.port), runtime)
    controller.set_runtime_observation(runtime_observation)
    server.timeout = 0.25
    receipt_written = False
    receipt_file_sha256: str | None = None
    print(f"MF-1750 N6 formal UI: {server.origin}/#token={server.security_token}")
    print("No device request occurs before browser conversion, four previews, allow, preflight, arm, and enqueue.")
    print("After a claim, there is at most one POST /api/frame and no retry/recovery.")
    print("Press Ctrl+C only after the UI reports protocol evidence or UNKNOWN_DO_NOT_RETRY.")
    try:
        while True:
            server.handle_request()
            receipt = controller.receipt
            if receipt is not None and not receipt_written:
                validate_n6_protocol_receipt(receipt, manifest=manifest)
                try:
                    receipt_file_sha256 = _write_new_json(
                        receipt_destination,
                        receipt,
                        label="N6 protocol receipt output",
                    )
                except N6VisibleOnceToolError as error:
                    raise N6PostClaimEvidenceUnknown(
                        "claim is consumed but protocol receipt persistence is unknown; do not rerun"
                    ) from error
                receipt_written = True
                print(
                    "N6 protocol receipt committed exclusively: "
                    f"{receipt_destination} ({receipt_file_sha256})"
                )
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    receipt = controller.receipt
    if receipt is None:
        return {
            "kind": "mf1750-n6-serve-cli-result",
            "state": "NO_ACTION_EXECUTED",
            "receipt_created": False,
            "claim_created_by_runner": False,
            "network_io_performed_by_runner": False,
            "device_io_performed_by_runner": False,
        }
    if not receipt_written:
        validate_n6_protocol_receipt(receipt, manifest=manifest)
        try:
            receipt_file_sha256 = _write_new_json(
                receipt_destination, receipt, label="N6 protocol receipt output"
            )
        except N6VisibleOnceToolError as error:
            raise N6PostClaimEvidenceUnknown(
                "claim is consumed but protocol receipt persistence is unknown; do not rerun"
            ) from error
    return {
        "kind": "mf1750-n6-serve-cli-result",
        "state": receipt["state"],
        "receipt_created": True,
        "protocol_receipt_canonical_sha256": receipt["integrity"][
            "canonical_sha256"
        ],
        "protocol_receipt_file_sha256": receipt_file_sha256,
        "frame_post_request_count": receipt["frame_post_request_count"],
        "retry_allowed": False,
        "recovery_allowed": False,
    }


def finalize_command(args: argparse.Namespace) -> Mapping[str, Any]:
    manifest = validate_n6_formal_manifest(
        _strict_json_file(args.manifest, label="N6 formal manifest")
    )
    receipt = validate_n6_protocol_receipt(
        _strict_json_file(args.receipt, label="N6 protocol receipt"),
        manifest=manifest,
    )
    _validate_disk_claim(manifest, receipt)
    if receipt["state"] == ResultState.UNKNOWN_DO_NOT_RETRY.value:
        if args.observation is not None:
            raise N6VisibleOnceToolError(
                "UNKNOWN receipt cannot accept a manual observation or promotion"
            )
        bundle = finalize_n6_unknown_receipt(
            manifest, receipt, finalized_at=args.finalized_at
        )
    else:
        if args.observation is None:
            raise N6VisibleOnceToolError(
                "protocol-verified receipt requires --observation"
            )
        observation_input = _strict_json_file(
            args.observation, label="N6 manual observation"
        )
        if "integrity" in observation_input:
            observation = validate_n6_manual_observation(
                observation_input,
                manifest=manifest,
                protocol_receipt=receipt,
            )
        else:
            operator_fields = {
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
            if set(observation_input) != operator_fields:
                raise N6VisibleOnceToolError(
                    "unsealed manual observation fields differ from the fixed operator template"
                )
            observation = seal_n6_manual_observation(
                {
                    "schema_version": 1,
                    "kind": MANUAL_OBSERVATION_KIND,
                    "formal_manifest_canonical_sha256": manifest["integrity"][
                        "canonical_sha256"
                    ],
                    "protocol_receipt_canonical_sha256": receipt["integrity"][
                        "canonical_sha256"
                    ],
                    "action_identity_sha256": manifest["action"][
                        "action_identity_sha256"
                    ],
                    "attempt_id": receipt["attempt_id"],
                    **observation_input,
                },
                manifest=manifest,
                protocol_receipt=receipt,
            )
        bundle = finalize_n6_manual_observation(
            manifest,
            receipt,
            observation,
            finalized_at=args.finalized_at,
        )
    file_sha256 = _write_new_json(
        args.output, bundle, label="N6 finalized bundle output"
    )
    return {
        "kind": "mf1750-n6-finalize-cli-result",
        "state": bundle["result"]["state"],
        "finalized_bundle_canonical_sha256": bundle["integrity"][
            "canonical_sha256"
        ],
        "finalized_bundle_file_sha256": file_sha256,
        "output": str(args.output),
        "terminal": True,
        "retry_allowed": False,
        "recovery_allowed": False,
    }


def validate_command(args: argparse.Namespace) -> Mapping[str, Any]:
    manifest = validate_n6_formal_manifest(
        _strict_json_file(args.manifest, label="N6 formal manifest")
    )
    output: dict[str, Any] = {
        "kind": "mf1750-n6-validate-cli-result",
        "formal_manifest_canonical_sha256": manifest["integrity"][
            "canonical_sha256"
        ],
        "formal_manifest_file_sha256": n6_formal_manifest_file_sha256(manifest),
        "valid": True,
        "network_io_performed": False,
        "device_io_performed": False,
    }
    if args.receipt is not None:
        receipt = validate_n6_protocol_receipt(
            _strict_json_file(args.receipt, label="N6 protocol receipt"),
            manifest=manifest,
        )
        output["protocol_receipt"] = {
            "state": receipt["state"],
            "canonical_sha256": receipt["integrity"]["canonical_sha256"],
            "frame_post_request_count": receipt["frame_post_request_count"],
        }
        output["workspace_global_claim"] = str(
            _validate_disk_claim(manifest, receipt)
        )
    if args.bundle is not None:
        bundle = validate_n6_finalized_bundle(
            _strict_json_file(args.bundle, label="N6 finalized bundle"),
            manifest=manifest,
        )
        claim_path = _validate_disk_claim(manifest, bundle["protocol_receipt"])
        output["finalized_bundle"] = {
            "state": bundle["result"]["state"],
            "canonical_sha256": bundle["integrity"]["canonical_sha256"],
            "file_sha256": n6_finalized_bundle_file_sha256(
                bundle, manifest=manifest
            ),
            "workspace_global_claim": str(claim_path),
        }
    return output


def _add_materialization_files(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--offline-manifest", type=Path, required=True)
    parser.add_argument("--palette-aggregate", type=Path)
    parser.add_argument("--gamut-profile", type=Path)
    parser.add_argument("--artifact-review", type=Path)
    parser.add_argument("--limit-profile", type=Path)
    parser.add_argument("--runtime-review", type=Path)
    parser.add_argument("--prior-result", type=Path)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    describe = subparsers.add_parser(
        "describe", help="describe missing static gates; zero claim/network/device I/O"
    )
    _add_materialization_files(describe)
    describe.add_argument("--evaluated-at", required=True)

    materialize = subparsers.add_parser(
        "materialize", help="freeze a complete reviewed formal manifest offline"
    )
    _add_materialization_files(materialize)
    materialize.add_argument("--materialized-at", required=True)
    materialize.add_argument("--output", type=Path, required=True)

    serve = subparsers.add_parser(
        "serve", help="serve the formal loopback UI for exactly one claimed action"
    )
    serve.add_argument("--manifest", type=Path, required=True)
    serve.add_argument("--authorization", type=Path, required=True)
    serve.add_argument("--runtime-observation", type=Path, required=True)
    serve.add_argument("--device-url", required=True)
    serve.add_argument("--attempt-id", required=True)
    serve.add_argument("--bind", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--receipt-output", type=Path, required=True)
    serve.add_argument("--confirm", required=True)

    finalize = subparsers.add_parser(
        "finalize", help="seal manual PASS/FAIL or terminal UNKNOWN offline"
    )
    finalize.add_argument("--manifest", type=Path, required=True)
    finalize.add_argument("--receipt", type=Path, required=True)
    finalize.add_argument("--observation", type=Path)
    finalize.add_argument("--finalized-at", required=True)
    finalize.add_argument("--output", type=Path, required=True)

    validate = subparsers.add_parser(
        "validate", help="deep-validate a manifest and optional receipt/bundle offline"
    )
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--receipt", type=Path)
    validate.add_argument("--bundle", type=Path)
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
            output = validate_command(args)
    except (N6ClaimConsumed, N6PostClaimUnknown, N6PostClaimEvidenceUnknown) as error:
        print(f"N6 visible-once UNKNOWN_DO_NOT_RETRY: {error}", file=sys.stderr)
        return 3
    except (N6VisibleExecutionError, N6VisibleOnceToolError, ValueError) as error:
        print(f"N6 visible-once error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
    if args.command == "serve" and output.get("state") == ResultState.UNKNOWN_DO_NOT_RETRY.value:
        return 3
    if args.command == "finalize" and output.get("state") == ResultState.FAIL.value:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "N6VisibleOnceToolError",
    "N6PostClaimEvidenceUnknown",
    "describe_command",
    "finalize_command",
    "main",
    "materialize_command",
    "parse_args",
    "serve_command",
    "validate_command",
]
