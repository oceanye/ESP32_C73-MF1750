#!/usr/bin/env python3
"""Build or validate one host-only C3 transition-optimization artifact.

There is intentionally no URL, serial port, claim, authorization, upload, or
visible-refresh path in this tool.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application.images import FitPolicy, decode_normalized_source  # noqa: E402
from host.color_pipeline import (  # noqa: E402
    DitherMode,
    PipelineOptions,
    RasterImage,
    load_palette,
)
from host.epd_frame import HEIGHT, WIDTH, unpack_pixels, validate_frame  # noqa: E402
from host.transition_optimizer import (  # noqa: E402
    MissingProfileMode,
    TransitionInputBinding,
    TransitionMetricWeights,
    TransitionOptimizationOptions,
    TransitionOptimizationResult,
    UnknownCurrentMode,
    build_pareto_report,
    optimize_transition_aware,
    validate_pareto_report,
    validate_transition_optimization_report,
)
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)


SCHEMA_VERSION = 1
MANIFEST_KIND = "mf1750-c3-transition-optimizer-offline-artifact-manifest"
MANIFEST_HASH_SCOPE = (
    "entire C3 artifact manifest excluding integrity; UTF-8 JSON with sorted "
    "keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
MANIFEST_FILENAME = "manifest.json"
FRAME_FILENAME = "frame.bin"
PREVIEW_FILENAME = "preview.png"
REPORT_FILENAME = "report.json"
PARETO_FILENAME = "pareto.json"
MAX_SOURCE_BYTES = 100 * 1024 * 1024
MAX_JSON_BYTES = 16 * 1024 * 1024


class TransitionArtifactError(ValueError):
    """A local input or output artifact failed closed."""


@dataclass(frozen=True)
class OfflineTransitionArtifacts:
    frame: bytes
    preview_png: bytes
    report: Mapping[str, Any]
    pareto_report: Optional[Mapping[str, Any]]
    manifest: Mapping[str, Any]


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise TransitionArtifactError(f"canonical JSON failed: {error}") from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _reject_reparse_chain(path: Path, *, label: str) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if not os.path.lexists(current):
            continue
        try:
            info = current.lstat()
        except OSError as error:
            raise TransitionArtifactError(f"cannot inspect {label}: {error}") from error
        attributes = getattr(info, "st_file_attributes", 0)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(info.st_mode) or attributes & reparse:
            raise TransitionArtifactError(f"{label} must not contain symlinks/reparse points")


def _safe_file(path: Path, *, label: str, maximum_bytes: int) -> tuple[Path, bytes]:
    try:
        require_local_regular_path_syntax(path, label=label)
        _reject_reparse_chain(path, label=label)
        resolved = path.resolve(strict=True)
        info = resolved.stat()
    except (LocalPathSafetyError, OSError) as error:
        raise TransitionArtifactError(f"invalid {label}: {error}") from error
    if not resolved.is_file() or info.st_size > maximum_bytes:
        raise TransitionArtifactError(f"{label} must be a regular file within size limit")
    try:
        payload = resolved.read_bytes()
    except OSError as error:
        raise TransitionArtifactError(f"cannot read {label}: {error}") from error
    return resolved, payload


def _json_bytes(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TransitionArtifactError(f"{label} must be strict UTF-8 JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise TransitionArtifactError(f"{label} must be a JSON object")
    if _canonical_bytes(value) != payload:
        raise TransitionArtifactError(f"{label} must use canonical JSON encoding")
    return value


def _binding(value: Optional[Mapping[str, Any]]) -> Optional[TransitionInputBinding]:
    if value is None:
        return None
    expected = {
        "binding_id",
        "palette_canonical_sha256",
        "palette_calibration_artifact_sha256",
        "transition_profile_canonical_sha256",
        "panel_serial",
        "firmware_binary_sha256",
        "waveform_sha256",
        "review_artifact_sha256",
    }
    if set(value) != expected:
        raise TransitionArtifactError("measurement binding fields changed")
    try:
        return TransitionInputBinding(**dict(value))
    except (TypeError, ValueError) as error:
        raise TransitionArtifactError(f"measurement binding is invalid: {error}") from error


def build_offline_artifacts(
    image: RasterImage,
    *,
    source_record: Mapping[str, Any],
    palette: Any,
    palette_file_sha256: str,
    transition_profile: Mapping[str, Any],
    transition_profile_file_sha256: str,
    current_codes: Optional[bytes],
    current_frame_file_sha256: Optional[str],
    measurement_binding: Optional[TransitionInputBinding],
    measurement_binding_file_sha256: Optional[str],
    options: TransitionOptimizationOptions,
    option_grid: Optional[Sequence[TransitionOptimizationOptions]] = None,
    allow_uncalibrated_palette: bool = False,
) -> OfflineTransitionArtifacts:
    """Build immutable bytes in memory; callers decide if and where to write."""

    if not isinstance(source_record, Mapping):
        raise TransitionArtifactError("source_record must be an object")
    result: TransitionOptimizationResult = optimize_transition_aware(
        image,
        palette=palette,
        transition_profile=transition_profile,
        current_codes=current_codes,
        measurement_binding=measurement_binding,
        options=options,
        allow_uncalibrated_palette=allow_uncalibrated_palette,
    )
    report = dict(validate_transition_optimization_report(result.report))
    preview = result.preview_png()
    pareto: Optional[Mapping[str, Any]] = None
    if option_grid is not None:
        if current_codes is None:
            raise TransitionArtifactError("Pareto grid requires an exact known current frame")
        pareto = build_pareto_report(
            image,
            palette=palette,
            transition_profile=transition_profile,
            current_codes=current_codes,
            measurement_binding=measurement_binding,
            option_grid=option_grid,
            allow_uncalibrated_palette=allow_uncalibrated_palette,
        )
        validate_pareto_report(pareto)
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "source": json.loads(_canonical_bytes(source_record).decode("utf-8")),
        "input_raster_sha256": report["input"]["raster_sha256"],
        "palette_canonical_sha256": report["palette"]["canonical_sha256"],
        "palette_file_sha256": palette_file_sha256,
        "transition_profile_canonical_sha256": report["transition_profile"][
            "canonical_sha256"
        ],
        "transition_profile_file_sha256": transition_profile_file_sha256,
        "current_frame_file_sha256": current_frame_file_sha256,
        "measurement_binding_file_sha256": measurement_binding_file_sha256,
        "artifacts": {
            FRAME_FILENAME: {"bytes": len(result.frame), "sha256": _sha256(result.frame)},
            PREVIEW_FILENAME: {"bytes": len(preview), "sha256": _sha256(preview)},
            REPORT_FILENAME: {
                "bytes": len(_canonical_bytes(report)),
                "sha256": _sha256(_canonical_bytes(report)),
            },
            PARETO_FILENAME: (
                None
                if pareto is None
                else {
                    "bytes": len(_canonical_bytes(pareto)),
                    "sha256": _sha256(_canonical_bytes(pareto)),
                }
            ),
        },
        "classification": {
            "offline_only": True,
            "network_io_performed": False,
            "device_io_performed": False,
            "claim_created": False,
            "authorization_created": False,
            "visible_refresh_authorized": False,
            "hardware_qualified": False,
            "busy_time_reduction_claim_allowed": False,
        },
    }
    manifest = {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(unsigned),
            "canonical_sha256_scope": MANIFEST_HASH_SCOPE,
        },
    }
    _validate_manifest(manifest)
    return OfflineTransitionArtifacts(result.frame, preview, report, pareto, manifest)


def _validate_manifest(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    expected = {
        "schema_version",
        "kind",
        "source",
        "input_raster_sha256",
        "palette_canonical_sha256",
        "palette_file_sha256",
        "transition_profile_canonical_sha256",
        "transition_profile_file_sha256",
        "current_frame_file_sha256",
        "measurement_binding_file_sha256",
        "artifacts",
        "classification",
        "integrity",
    }
    if not isinstance(manifest, Mapping) or set(manifest) != expected:
        raise TransitionArtifactError("artifact manifest fields changed")
    if manifest["schema_version"] != SCHEMA_VERSION or manifest["kind"] != MANIFEST_KIND:
        raise TransitionArtifactError("artifact manifest schema changed")
    unsigned = dict(manifest)
    integrity = unsigned.pop("integrity")
    if integrity != {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": MANIFEST_HASH_SCOPE,
    }:
        raise TransitionArtifactError("artifact manifest integrity is invalid")
    if manifest["classification"] != {
        "offline_only": True,
        "network_io_performed": False,
        "device_io_performed": False,
        "claim_created": False,
        "authorization_created": False,
        "visible_refresh_authorized": False,
        "hardware_qualified": False,
        "busy_time_reduction_claim_allowed": False,
    }:
        raise TransitionArtifactError("artifact safety classification changed")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, Mapping) or set(artifacts) != {
        FRAME_FILENAME,
        PREVIEW_FILENAME,
        REPORT_FILENAME,
        PARETO_FILENAME,
    }:
        raise TransitionArtifactError("artifact inventory changed")
    return manifest


def _atomic_new_file(directory: Path, name: str, payload: bytes) -> None:
    path = directory / name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise TransitionArtifactError(f"refusing to overwrite {path}") from error
    except OSError as error:
        raise TransitionArtifactError(f"cannot write {path}: {error}") from error


def write_offline_artifacts(
    output_directory: Path, artifacts: OfflineTransitionArtifacts
) -> Path:
    if not isinstance(output_directory, Path):
        raise TransitionArtifactError("output_directory must be pathlib.Path")
    try:
        require_local_regular_path_syntax(output_directory, label="C3 output directory")
        if os.path.lexists(output_directory):
            raise TransitionArtifactError("output directory already exists")
        _reject_reparse_chain(output_directory.parent, label="C3 output parent")
        parent = output_directory.parent.resolve(strict=True)
    except (LocalPathSafetyError, OSError) as error:
        raise TransitionArtifactError(f"invalid output directory: {error}") from error
    if not parent.is_dir():
        raise TransitionArtifactError("output parent must be a directory")
    destination = parent / output_directory.name
    destination.mkdir()
    _atomic_new_file(destination, FRAME_FILENAME, artifacts.frame)
    _atomic_new_file(destination, PREVIEW_FILENAME, artifacts.preview_png)
    _atomic_new_file(destination, REPORT_FILENAME, _canonical_bytes(artifacts.report))
    if artifacts.pareto_report is not None:
        _atomic_new_file(
            destination, PARETO_FILENAME, _canonical_bytes(artifacts.pareto_report)
        )
    _atomic_new_file(destination, MANIFEST_FILENAME, _canonical_bytes(artifacts.manifest))
    validate_offline_artifact_directory(destination)
    return destination


def validate_offline_artifact_directory(directory: Path) -> Mapping[str, Any]:
    try:
        require_local_regular_path_syntax(directory, label="C3 artifact directory")
        _reject_reparse_chain(directory, label="C3 artifact directory")
        root = directory.resolve(strict=True)
    except (LocalPathSafetyError, OSError) as error:
        raise TransitionArtifactError(f"invalid artifact directory: {error}") from error
    if not root.is_dir():
        raise TransitionArtifactError("artifact path is not a directory")
    manifest_path, manifest_payload = _safe_file(
        root / MANIFEST_FILENAME,
        label="C3 artifact manifest",
        maximum_bytes=MAX_JSON_BYTES,
    )
    if manifest_path.parent != root:
        raise TransitionArtifactError("manifest escaped artifact directory")
    manifest = _validate_manifest(_json_bytes(manifest_payload, label="artifact manifest"))
    expected_files = {MANIFEST_FILENAME, FRAME_FILENAME, PREVIEW_FILENAME, REPORT_FILENAME}
    if manifest["artifacts"][PARETO_FILENAME] is not None:
        expected_files.add(PARETO_FILENAME)
    actual_files = {path.name for path in root.iterdir() if path.is_file()}
    if actual_files != expected_files or any(path.is_dir() for path in root.iterdir()):
        raise TransitionArtifactError("artifact directory inventory changed")
    payloads: dict[str, bytes] = {}
    for name in expected_files - {MANIFEST_FILENAME}:
        _path, payload = _safe_file(
            root / name,
            label=f"C3 artifact {name}",
            maximum_bytes=MAX_SOURCE_BYTES,
        )
        payloads[name] = payload
        record = manifest["artifacts"][name]
        if record != {"bytes": len(payload), "sha256": _sha256(payload)}:
            raise TransitionArtifactError(f"artifact identity changed: {name}")
    report = validate_transition_optimization_report(
        _json_bytes(payloads[REPORT_FILENAME], label="optimization report")
    )
    if (
        report["output"]["frame_sha256"] != _sha256(payloads[FRAME_FILENAME])
        or report["output"]["frame_bytes"] != len(payloads[FRAME_FILENAME])
    ):
        raise TransitionArtifactError("frame/report binding changed")
    if PARETO_FILENAME in payloads:
        validate_pareto_report(
            _json_bytes(payloads[PARETO_FILENAME], label="Pareto report")
        )
    return manifest


def _option_grid(
    payload: Optional[bytes], base: TransitionOptimizationOptions
) -> Optional[list[TransitionOptimizationOptions]]:
    if payload is None:
        return None
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TransitionArtifactError(f"Pareto grid is invalid JSON: {error}") from error
    if not isinstance(value, list) or not value:
        raise TransitionArtifactError("Pareto grid must be a non-empty JSON array")
    points = []
    for index, point in enumerate(value):
        if not isinstance(point, Mapping) or set(point) != {"alpha", "beta", "gamma", "delta"}:
            raise TransitionArtifactError(
                f"Pareto grid point {index} must contain alpha/beta/gamma/delta"
            )
        points.append(
            TransitionOptimizationOptions(
                alpha=point["alpha"],
                beta=point["beta"],
                gamma=point["gamma"],
                delta=point["delta"],
                metric_weights=base.metric_weights,
                pipeline_options=base.pipeline_options,
                missing_profile_mode=base.missing_profile_mode,
                unknown_current_mode=base.unknown_current_mode,
            )
        )
    return points


def _build(args: argparse.Namespace) -> Mapping[str, Any]:
    _source_path, source = _safe_file(
        args.source, label="source image", maximum_bytes=MAX_SOURCE_BYTES
    )
    decoded = decode_normalized_source(
        source,
        args.media_type,
        args.fit,
        rotation_degrees=args.rotation_degrees,
    )
    palette_path, palette_payload = _safe_file(
        args.palette, label="palette", maximum_bytes=MAX_JSON_BYTES
    )
    palette = load_palette(palette_path)
    _profile_path, profile_payload = _safe_file(
        args.transition_profile,
        label="transition profile",
        maximum_bytes=MAX_JSON_BYTES,
    )
    profile = _json_bytes(profile_payload, label="transition profile")
    current_codes = None
    current_sha = None
    if args.current_frame is not None:
        _current_path, current_frame = _safe_file(
            args.current_frame, label="current frame", maximum_bytes=MAX_SOURCE_BYTES
        )
        validate_frame(current_frame)
        current_codes = bytes(unpack_pixels(current_frame, WIDTH, HEIGHT))
        current_sha = _sha256(current_frame)
    binding = None
    binding_sha = None
    if args.measurement_binding is not None:
        _binding_path, binding_payload = _safe_file(
            args.measurement_binding,
            label="measurement binding",
            maximum_bytes=MAX_JSON_BYTES,
        )
        binding = _binding(_json_bytes(binding_payload, label="measurement binding"))
        binding_sha = _sha256(binding_payload)
    pipeline = PipelineOptions(
        dither=args.dither,
        seed=args.seed,
        serpentine=not args.no_serpentine,
        white_protection=not args.disable_white_protection,
        preserve_edges=args.preserve_edges,
        text_mode=False,
    )
    metric_weights = TransitionMetricWeights(
        optical=args.cost_optical,
        peak_current=args.cost_peak_current,
        energy=args.cost_energy,
        settling=args.cost_settling,
        ghosting=args.cost_ghosting,
        temperature=args.cost_temperature,
        recovery_failure=args.cost_recovery_failure,
    )
    options = TransitionOptimizationOptions(
        alpha=args.alpha,
        beta=args.beta,
        gamma=args.gamma,
        delta=args.delta,
        metric_weights=metric_weights,
        pipeline_options=pipeline,
        missing_profile_mode=args.missing_profile_mode,
        unknown_current_mode=args.unknown_current_mode,
    )
    grid_payload = None
    if args.pareto_grid is not None:
        _grid_path, grid_payload = _safe_file(
            args.pareto_grid, label="Pareto grid", maximum_bytes=MAX_JSON_BYTES
        )
    artifacts = build_offline_artifacts(
        decoded.raster,
        source_record={
            "source_file_sha256": decoded.source_sha256,
            "declared_media_type": args.media_type,
            "decode_provenance": decoded.provenance,
        },
        palette=palette,
        palette_file_sha256=_sha256(palette_payload),
        transition_profile=profile,
        transition_profile_file_sha256=_sha256(profile_payload),
        current_codes=current_codes,
        current_frame_file_sha256=current_sha,
        measurement_binding=binding,
        measurement_binding_file_sha256=binding_sha,
        options=options,
        option_grid=_option_grid(grid_payload, options),
        allow_uncalibrated_palette=args.allow_uncalibrated_palette,
    )
    output = write_offline_artifacts(args.output_directory, artifacts)
    return validate_offline_artifact_directory(output)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build one offline C3 artifact")
    build.add_argument("--source", type=Path, required=True)
    build.add_argument(
        "--media-type", choices=("image/png", "image/jpeg", "image/webp"), required=True
    )
    build.add_argument("--fit", choices=tuple(item.value for item in FitPolicy), default="contain")
    build.add_argument("--rotation-degrees", type=int, choices=(0, 90, 180, 270), default=0)
    build.add_argument("--palette", type=Path, required=True)
    build.add_argument("--transition-profile", type=Path, required=True)
    build.add_argument("--current-frame", type=Path)
    build.add_argument("--measurement-binding", type=Path)
    build.add_argument("--pareto-grid", type=Path)
    build.add_argument("--output-directory", type=Path, required=True)
    build.add_argument("--alpha", type=float, default=1.0)
    build.add_argument("--beta", type=float, default=1.0)
    build.add_argument("--gamma", type=float, default=0.0)
    build.add_argument("--delta", type=float, default=0.0)
    build.add_argument(
        "--dither",
        choices=(DitherMode.FLOYD_STEINBERG.value, DitherMode.ATKINSON.value),
        default=DitherMode.FLOYD_STEINBERG.value,
    )
    build.add_argument("--seed", type=lambda value: int(value, 0), default=0x4D463137)
    build.add_argument("--no-serpentine", action="store_true")
    build.add_argument("--disable-white-protection", action="store_true")
    build.add_argument("--preserve-edges", action="store_true")
    build.add_argument("--allow-uncalibrated-palette", action="store_true")
    build.add_argument(
        "--missing-profile-mode",
        choices=tuple(item.value for item in MissingProfileMode),
        default=MissingProfileMode.REJECT.value,
    )
    build.add_argument(
        "--unknown-current-mode",
        choices=tuple(item.value for item in UnknownCurrentMode),
        default=UnknownCurrentMode.REJECT.value,
    )
    for name in (
        "optical",
        "peak-current",
        "energy",
        "settling",
        "ghosting",
        "temperature",
        "recovery-failure",
    ):
        build.add_argument(f"--cost-{name}", type=float, default=1.0)
    validate = subparsers.add_parser("validate", help="deep-validate an artifact directory")
    validate.add_argument("directory", type=Path)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = (
            _build(args)
            if args.command == "build"
            else validate_offline_artifact_directory(args.directory)
        )
    except (TransitionArtifactError, ValueError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(_canonical_bytes(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
