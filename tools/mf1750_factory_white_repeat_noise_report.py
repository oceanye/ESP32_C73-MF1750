#!/usr/bin/env python3
"""Seal a locked-camera factory-white repeat-noise baseline.

This program is deliberately offline.  It deep-validates three or more
``live_synchronized`` full-panel camera sidecars, requires every frame to be
bound to the same completed factory-white action and locked camera setup, and
then measures camera-relative CIE76 variation over the existing panel-wide
60-patch geometry.  It never opens a camera or accesses the display, relay,
serial port, or network.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from itertools import combinations
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np

from tools import mf1750_camera_capture_evidence as camera
from tools import mf1750_factory_white_reference_photo_gate as white
from tools import mf1750_same_r20_atlas_photo_analyzer as common
from tools import mf1750_true_r20_hold_photo_gate as static_gate


SCHEMA_VERSION = 1
KIND = "mf1750-factory-white-locked-camera-repeat-noise-baseline-v1"
INTEGRITY_ALGORITHM = common.INTEGRITY_ALGORITHM
MINIMUM_CAPTURE_COUNT = 3
MANUAL_CONTROL_REQUESTS = {
    "autofocus": 0.0,
    "auto_exposure": 0.25,
    "auto_white_balance": 0.0,
}
DSHOW_MANUAL_RAW_VALUES = {
    "autofocus": (0.0, 2.0),
    "auto_exposure": (-1.0, 0.25),
    "auto_white_balance": (0.0,),
}
LOCKED_NUMERIC_FIELDS = ("focus", "exposure", "white_balance_temperature")


class FactoryWhiteRepeatNoiseReportError(RuntimeError):
    """Raised when a repeat-noise input or exclusive output is invalid."""


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FactoryWhiteRepeatNoiseReportError(
            f"record contains a non-canonical JSON value: {exc}"
        ) from exc


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FactoryWhiteRepeatNoiseReportError(f"{label} must be an object")
    return value


def _finite_number(value: Any, *, label: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise FactoryWhiteRepeatNoiseReportError(
            f"{label} must be an explicit finite number"
        )
    return float(value)


def _require_locked_settings(
    requested: Mapping[str, Any],
    effective: Mapping[str, Any],
    *,
    backend: Any,
    label: str,
) -> dict[str, Any]:
    if not isinstance(backend, str) or not backend.strip():
        raise FactoryWhiteRepeatNoiseReportError(
            f"{label}.backend must be a non-empty string"
        )
    backend_name = backend.strip()
    is_known_dshow = backend_name.upper() == "DSHOW"

    effective_raw_modes: dict[str, float] = {}
    accepted_raw_values: dict[str, tuple[float, ...]] = {}
    normalization_used = False
    for field, expected in MANUAL_CONTROL_REQUESTS.items():
        requested_value = _finite_number(requested.get(field), label=f"{label}.{field}")
        if requested_value != expected:
            if field == "autofocus":
                reason = "must explicitly request manual focus"
            elif field == "auto_white_balance":
                reason = "must explicitly request manual white balance"
            else:
                reason = f"must equal the locked manual request {expected:g}"
            raise FactoryWhiteRepeatNoiseReportError(f"{label}.{field} {reason}")

        accepted = DSHOW_MANUAL_RAW_VALUES[field] if is_known_dshow else (expected,)
        effective_value = _finite_number(
            effective.get(field), label=f"{label}.effective.{field}"
        )
        if effective_value not in accepted:
            raise FactoryWhiteRepeatNoiseReportError(
                f"{label}.effective.{field} raw value {effective_value:g} is not "
                f"an accepted {backend_name} manual-mode encoding"
            )
        accepted_raw_values[field] = accepted
        effective_raw_modes[field] = effective_value
        normalization_used = normalization_used or effective_value != expected

    for field in LOCKED_NUMERIC_FIELDS:
        _finite_number(requested.get(field), label=f"{label}.{field}")
        _finite_number(effective.get(field), label=f"{label}.effective.{field}")

    return {
        "policy": (
            "DSHOW_DRIVER_SPECIFIC_RAW_ENUM_V1"
            if is_known_dshow
            else "EXACT_REQUESTED_VALUE_V1"
        ),
        "backend": backend_name,
        "effective_raw_values": effective_raw_modes,
        "accepted_raw_values": {
            field: list(values) for field, values in accepted_raw_values.items()
        },
        "normalized_manual_state": {field: True for field in MANUAL_CONTROL_REQUESTS},
        "driver_specific_normalization_used": normalization_used,
    }


def _percentile(values: Sequence[float], percentile: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.float64), percentile))


def _distribution(values: Sequence[float]) -> dict[str, float | int]:
    if not values:
        raise FactoryWhiteRepeatNoiseReportError("noise distribution is empty")
    data = np.asarray(values, dtype=np.float64)
    if not np.all(np.isfinite(data)):
        raise FactoryWhiteRepeatNoiseReportError(
            "noise distribution contains a non-finite value"
        )
    return {
        "sample_count": int(data.size),
        "mean": float(np.mean(data)),
        "standard_deviation": float(np.std(data)),
        "median": float(np.median(data)),
        "p90": _percentile(values, 90),
        "p95": _percentile(values, 95),
        "p99": _percentile(values, 99),
        "maximum": float(np.max(data)),
    }


def _sidecar_photo_path(sidecar_path: Path, root: Mapping[str, Any]) -> Path:
    photo = _mapping(root.get("photo"), label="capture sidecar photo")
    try:
        return camera._resolve_evidence_path(
            photo.get("path"),
            sidecar_path=sidecar_path,
            label="capture sidecar photo.path",
        )
    except camera.CameraCaptureEvidenceError as exc:
        raise FactoryWhiteRepeatNoiseReportError(str(exc)) from exc


def build_report(
    reference_grid_path: Path, capture_sidecars: Sequence[Path]
) -> dict[str, Any]:
    """Return a sealed repeat-noise baseline without performing device I/O."""

    sidecar_paths = [Path(path) for path in capture_sidecars]
    if len(sidecar_paths) < MINIMUM_CAPTURE_COUNT:
        raise FactoryWhiteRepeatNoiseReportError(
            f"at least {MINIMUM_CAPTURE_COUNT} capture sidecars are required"
        )
    resolved_sidecars = [path.resolve() for path in sidecar_paths]
    if len(set(resolved_sidecars)) != len(resolved_sidecars):
        raise FactoryWhiteRepeatNoiseReportError(
            "capture sidecar paths must be distinct"
        )

    try:
        reference_payload, reference_root, homography, dimensions = (
            static_gate._load_reference(Path(reference_grid_path))
        )
        reference_integrity = common._verify_integrity(reference_root)
    except (
        static_gate.TrueR20HoldPhotoGateError,
        common.SameR20AtlasAnalysisError,
    ) as exc:
        raise FactoryWhiteRepeatNoiseReportError(str(exc)) from exc

    records: list[dict[str, Any]] = []
    rectified_images: list[np.ndarray] = []
    setup_identity: dict[str, Any] | None = None
    action_identity: dict[str, Any] | None = None
    observed_photo_hashes: set[str] = set()
    observed_capture_ids: set[str] = set()
    observed_capture_times: set[str] = set()

    for index, sidecar_path in enumerate(sidecar_paths, 1):
        try:
            root = camera.validate_capture_evidence(sidecar_path)
            sidecar_payload = camera._read_stable_regular(
                sidecar_path, label=f"capture sidecar {index}"
            )
        except camera.CameraCaptureEvidenceError as exc:
            raise FactoryWhiteRepeatNoiseReportError(str(exc)) from exc

        coverage = _mapping(root.get("coverage"), label=f"sidecar {index}.coverage")
        if (
            root.get("capture_binding") != camera.BINDING_LIVE
            or coverage.get("scope") != camera.COVERAGE_FULL
            or coverage.get("full_panel_visible") is not True
            or coverage.get("full_panel_uncropped") is not True
        ):
            raise FactoryWhiteRepeatNoiseReportError(
                f"sidecar {index} must be live_synchronized full-panel evidence"
            )
        role = root.get("role")
        if (
            not isinstance(role, str)
            or "FACTORY" not in role.upper()
            or "WHITE" not in role.upper()
        ):
            raise FactoryWhiteRepeatNoiseReportError(
                f"sidecar {index} is not bound to a factory-white action"
            )
        action_result = _mapping(
            root.get("action_result"), label=f"sidecar {index}.action_result"
        )
        if action_result.get("visible_refreshes") != 1:
            raise FactoryWhiteRepeatNoiseReportError(
                f"sidecar {index} factory-white action must have one visible refresh"
            )

        camera_record = _mapping(root.get("camera"), label=f"sidecar {index}.camera")
        requested = _mapping(
            camera_record.get("requested_settings"),
            label=f"sidecar {index}.camera.requested_settings",
        )
        before = _mapping(
            camera_record.get("effective_settings_before_frame"),
            label=f"sidecar {index}.camera.effective_settings_before_frame",
        )
        after = _mapping(
            camera_record.get("effective_settings_after_frame"),
            label=f"sidecar {index}.camera.effective_settings_after_frame",
        )
        if dict(before) != dict(after):
            raise FactoryWhiteRepeatNoiseReportError(
                f"sidecar {index} effective settings changed around the frame"
            )
        backend = camera_record.get("backend")
        manual_mode_normalization = _require_locked_settings(
            requested,
            before,
            backend=backend,
            label=f"sidecar {index}.camera",
        )

        current_setup = {
            "camera_id": camera_record.get("camera_id"),
            "camera_instance_id": camera_record.get("instance_id"),
            "camera_index": camera_record.get("index"),
            "backend": backend,
            "mount_id": coverage.get("mount_id"),
            "requested_settings": dict(requested),
            "effective_settings": dict(before),
            "manual_mode_readback_normalization": manual_mode_normalization,
        }
        if setup_identity is None:
            setup_identity = current_setup
        elif current_setup != setup_identity:
            raise FactoryWhiteRepeatNoiseReportError(
                f"sidecar {index} camera, mount, or locked settings differ"
            )

        current_action = {
            "campaign_id": root.get("campaign_id"),
            "test_id": root.get("test_id"),
            "contract_id": root.get("contract_id"),
            "firmware_sha256": root.get("firmware_sha256"),
            "boot_nonce": root.get("boot_nonce"),
            "ordinal": root.get("ordinal"),
            "action_id": root.get("action_id"),
            "descriptor_id": root.get("descriptor_id"),
            "role": role,
            "frame_sha256": root.get("frame_sha256"),
            "action_result_file_sha256": action_result.get("file_sha256"),
        }
        if action_identity is None:
            action_identity = current_action
        elif current_action != action_identity:
            raise FactoryWhiteRepeatNoiseReportError(
                f"sidecar {index} is not bound to the same factory-white action"
            )

        photo_record = _mapping(root.get("photo"), label=f"sidecar {index}.photo")
        photo_path = _sidecar_photo_path(sidecar_path, root)
        try:
            photo_payload = camera._read_stable_regular(
                photo_path, label=f"factory-white repeat photo {index}"
            )
            _, photo_image = static_gate._decode(
                photo_path, dimensions, label=f"factory-white repeat photo {index}"
            )
            rectified = static_gate._rectify(photo_image, homography)
        except (
            camera.CameraCaptureEvidenceError,
            static_gate.TrueR20HoldPhotoGateError,
        ) as exc:
            raise FactoryWhiteRepeatNoiseReportError(str(exc)) from exc
        photo_sha256 = _sha256_bytes(photo_payload)
        if photo_record.get("sha256") != photo_sha256:
            raise FactoryWhiteRepeatNoiseReportError(
                f"sidecar {index} photo SHA-256 differs after validation"
            )
        if photo_sha256 in observed_photo_hashes:
            raise FactoryWhiteRepeatNoiseReportError(
                "factory-white repeat photos must contain distinct bytes"
            )
        capture_id = root.get("capture_id")
        captured_at = root.get("captured_at")
        if not isinstance(capture_id, str) or capture_id in observed_capture_ids:
            raise FactoryWhiteRepeatNoiseReportError("capture IDs must be distinct")
        if not isinstance(captured_at, str) or captured_at in observed_capture_times:
            raise FactoryWhiteRepeatNoiseReportError("capture times must be distinct")
        observed_photo_hashes.add(photo_sha256)
        observed_capture_ids.add(capture_id)
        observed_capture_times.add(captured_at)
        rectified_images.append(rectified)
        integrity = _mapping(root.get("integrity"), label=f"sidecar {index}.integrity")
        records.append(
            {
                "capture_index": index,
                "sidecar": {
                    "path": str(sidecar_path),
                    "bytes": len(sidecar_payload),
                    "file_sha256": _sha256_bytes(sidecar_payload),
                    "canonical_integrity_sha256": integrity.get("sha256"),
                },
                "capture_id": capture_id,
                "captured_at": captured_at,
                "photo": {
                    "path": str(photo_path),
                    "bytes": len(photo_payload),
                    "sha256": photo_sha256,
                    "width": photo_record.get("width"),
                    "height": photo_record.get("height"),
                },
            }
        )

    if setup_identity is None or action_identity is None:
        raise FactoryWhiteRepeatNoiseReportError(
            "validated capture set unexpectedly produced no identity"
        )

    samples: list[dict[str, Any]] = []
    sample_labs: dict[tuple[int, int, int], list[float]] = {}
    for capture_index, image in enumerate(rectified_images, 1):
        for controller in range(2):
            for row in range(white.ROWS):
                for column in range(white.COLUMNS_PER_CONTROLLER):
                    bounds = white._bounds(controller, row, column)
                    lab = static_gate._median_lab(image, bounds).astype(float).tolist()
                    sample_labs[(capture_index, controller, row, column)] = lab
                    samples.append(
                        {
                            "capture_index": capture_index,
                            "controller": controller,
                            "row": row,
                            "column": column,
                            "logical_bounds": list(bounds),
                            "camera_relative_lab": lab,
                        }
                    )

    pair_records: list[dict[str, Any]] = []
    patch_deltas: dict[tuple[int, int, int], list[float]] = {
        (controller, row, column): []
        for controller in range(2)
        for row in range(white.ROWS)
        for column in range(white.COLUMNS_PER_CONTROLLER)
    }
    all_deltas: list[float] = []
    for first, second in combinations(range(1, len(rectified_images) + 1), 2):
        pair_values: list[float] = []
        for key in patch_deltas:
            first_lab = np.asarray(sample_labs[(first, *key)], dtype=np.float64)
            second_lab = np.asarray(sample_labs[(second, *key)], dtype=np.float64)
            delta = float(np.linalg.norm(first_lab - second_lab))
            patch_deltas[key].append(delta)
            pair_values.append(delta)
            all_deltas.append(delta)
        pair_records.append(
            {
                "first_capture_index": first,
                "second_capture_index": second,
                "distribution_de76": _distribution(pair_values),
            }
        )

    patch_records: list[dict[str, Any]] = []
    for (controller, row, column), values in patch_deltas.items():
        patch_records.append(
            {
                "controller": controller,
                "row": row,
                "column": column,
                "logical_bounds": list(white._bounds(controller, row, column)),
                "distribution_de76": _distribution(values),
            }
        )

    distribution = _distribution(all_deltas)
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "baseline_id": _sha256_bytes(
            _canonical_json(
                {
                    "reference_grid_sha256": _sha256_bytes(reference_payload),
                    "capture_sidecar_file_sha256": [
                        item["sidecar"]["file_sha256"] for item in records
                    ],
                    "method": "all-unordered-photo-pairs-panel-wide-60-patch-de76-v1",
                }
            )
        ),
        "layout": {
            "id": white.LAYOUT_ID,
            "controllers": 2,
            "rows": white.ROWS,
            "columns_per_controller": white.COLUMNS_PER_CONTROLLER,
            "patch_count": len(patch_records),
            "full_logical_width": common.LOGICAL_WIDTH,
            "full_logical_height": common.LOGICAL_HEIGHT,
            "same_reference_homography_for_every_capture": True,
        },
        "geometry_reference": {
            "path": str(reference_grid_path),
            "bytes": len(reference_payload),
            "file_sha256": _sha256_bytes(reference_payload),
            "canonical_integrity_sha256": reference_integrity,
        },
        "capture_contract": {
            "minimum_capture_count": MINIMUM_CAPTURE_COUNT,
            "capture_count": len(records),
            "pair_count": len(pair_records),
            "capture_binding": camera.BINDING_LIVE,
            "coverage_scope": camera.COVERAGE_FULL,
            "same_factory_white_action": True,
            "distinct_capture_ids": True,
            "distinct_capture_times": True,
            "distinct_photo_sha256": True,
            "locked_camera_and_mount": setup_identity,
            "factory_white_action": action_identity,
        },
        "captures": records,
        "method": {
            "name": "all-unordered-photo-pairs-panel-wide-60-patch-de76-v1",
            "colour_space": "OpenCV camera-relative CIE Lab",
            "distance": "CIE76 Euclidean Lab distance",
            "pairwise_samples_per_photo_pair": len(patch_records),
        },
        "lab_samples": samples,
        "photo_pair_distributions": pair_records,
        "patch_distributions": patch_records,
        "summary": {
            "repeat_noise_p95_de76": distribution["p95"],
            "distribution_de76": distribution,
        },
        "classification": {
            "state": "LOCKED_CAMERA_FACTORY_WHITE_REPEAT_NOISE_BASELINE",
            "valid_repeat_noise_baseline": True,
            "absolute_white_proven": False,
            "calibrated_de00_proven": False,
        },
        "evidence_boundaries": {
            "camera_relative_cie76_not_calibrated_de00": True,
            "pairwise_frame_variation_includes_camera_and_jpeg_noise": True,
            "discrete_60_patch_grid_not_every_pixel": True,
            "same_action_binding_does_not_independently_prove_no_intervening_refresh": True,
            "recorded_settings_do_not_physically_prove_camera_mount_immutability": True,
            "device_camera_network_serial_relay_io_performed_by_reporter": False,
        },
        "output_write_contract": "O_EXCL",
    }
    unsigned["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _sha256_bytes(_canonical_json(unsigned)),
    }
    return unsigned


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--reference-grid-analysis", type=Path, required=True)
    parser.add_argument("--capture-sidecar", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = build_report(args.reference_grid_analysis, args.capture_sidecar)
        payload = (
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode(
                "utf-8"
            )
            + b"\n"
        )
        common._write_exclusive(args.output, payload)
        sys.stdout.buffer.write(payload)
        return 0
    except (
        FactoryWhiteRepeatNoiseReportError,
        common.SameR20AtlasAnalysisError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
