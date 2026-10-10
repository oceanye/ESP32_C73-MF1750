#!/usr/bin/env python3
"""Build or deep-validate the offline MF1750 dither-effects extension bundle."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host import dither_effects_suite as suite  # noqa: E402
from host.color_pipeline.preview import encode_rgb_png  # noqa: E402
from host.epd_frame import HEIGHT, WIDTH, unpack_pixels  # noqa: E402


BUNDLE_KIND = "mf1750-ec5-dither-effects-extension-offline-bundle"
OBSERVATION_TEMPLATE_KIND = "mf1750-ec5-dither-effects-extension-observation-template"
MAX_FILE_BYTES = 16 * 1024 * 1024
EXPECTED_FILES = frozenset(
    {
        "pair-gradients.frame.bin",
        "effects-chart.frame.bin",
        "white.frame.bin",
        "pair-gradients-strict-preview.png",
        "effects-chart-strict-preview.png",
        "layout.json",
        "operator-observation-template.json",
        "operator-card.md",
        "bundle-manifest.json",
    }
)


class DitherEffectsBundleError(RuntimeError):
    """The effects bundle is incomplete, inconsistent, or unsafe to create."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise DitherEffectsBundleError(
            f"value is not canonical JSON: {error}"
        ) from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(unsigned))
    result["integrity"] = {
        "canonical_sha256": _sha256(_canonical(unsigned)),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    return result


def _strict_json(payload: bytes, *, label: str) -> Mapping[str, Any]:
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DitherEffectsBundleError(
                    f"{label} contains duplicate key {key!r}"
                )
            result[key] = value
        return result

    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicate,
            parse_constant=lambda token: (_ for _ in ()).throw(
                DitherEffectsBundleError(f"{label} contains forbidden {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DitherEffectsBundleError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(root, Mapping):
        raise DitherEffectsBundleError(f"{label} root must be an object")
    return root


def _validate_seal(root: Mapping[str, Any], *, label: str) -> None:
    integrity = root.get("integrity")
    if not isinstance(integrity, Mapping) or set(integrity) != {
        "canonical_sha256",
        "scope",
    }:
        raise DitherEffectsBundleError(f"{label} integrity fields differ")
    unsigned = dict(root)
    unsigned.pop("integrity")
    expected = {
        "canonical_sha256": _sha256(_canonical(unsigned)),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    if dict(integrity) != expected:
        raise DitherEffectsBundleError(f"{label} integrity differs")


def _read_regular(path: Path, *, label: str) -> bytes:
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise DitherEffectsBundleError(
                f"{label} must be a regular non-symlink file"
            )
        if not 0 < before.st_size <= MAX_FILE_BYTES:
            raise DitherEffectsBundleError(f"{label} size is invalid")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise DitherEffectsBundleError(f"could not read {label}: {error}") from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or len(payload) != after.st_size:
        raise DitherEffectsBundleError(f"{label} changed while read")
    return payload


def _write_new(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise DitherEffectsBundleError(f"refusing to overwrite {path}") from error
    except OSError as error:
        raise DitherEffectsBundleError(f"could not write {path}: {error}") from error


def _create_directory(path: Path) -> Path:
    if os.path.lexists(path):
        raise DitherEffectsBundleError("output directory already exists")
    try:
        parent_meta = path.parent.lstat()
        parent = path.parent.resolve(strict=True)
        if stat.S_ISLNK(parent_meta.st_mode) or not stat.S_ISDIR(parent_meta.st_mode):
            raise DitherEffectsBundleError(
                "output parent must be a non-symlink directory"
            )
        directory = parent / path.name
        directory.mkdir()
        metadata = directory.lstat()
    except OSError as error:
        raise DitherEffectsBundleError(
            f"could not create output directory: {error}"
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise DitherEffectsBundleError("created output is not a regular directory")
    return directory


def _strict_preview(role: str) -> bytes:
    codes = unpack_pixels(suite.build_frame(role))
    rgb = bytearray(len(codes) * 3)
    for index, code in enumerate(codes):
        color = suite.NOMINAL_RGB_BY_CODE[code]
        target = index * 3
        rgb[target : target + 3] = bytes(color)
    return encode_rgb_png(WIDTH, HEIGHT, rgb)


def _observation_template() -> dict[str, Any]:
    gradient_rows = []
    for index, family in enumerate(suite.MIX_FAMILIES):
        gradient_rows.append(
            {
                "display_row": index,
                "row_id": family.row_id,
                "appearance_hypothesis": family.appearance_hypothesis,
                "native_pair": [family.color_a, family.color_b],
                "near_view_20_to_30_cm": {
                    "ordered_pixel_texture_visible": None,
                    "unexpected_vertical_or_horizontal_artifact": None,
                    "operator_words": None,
                },
                "mid_view_about_1_m": {
                    "transition_is_visually_monotonic": None,
                    "obvious_banding_count_or_none": None,
                    "intermediate_hues_visible": None,
                    "operator_words": None,
                },
                "left_right_halves_match": None,
            }
        )
    return _seal(
        {
            "schema_version": 1,
            "kind": OBSERVATION_TEMPLATE_KIND,
            "layout_canonical_sha256": suite.layout_manifest()["integrity"][
                "canonical_sha256"
            ],
            "not_a_completed_observation": True,
            "pair_gradients": {
                "matches_strict_preview_geometry": None,
                "white_margins_clean": None,
                "rows": gradient_rows,
            },
            "effects_chart": {
                "matches_strict_preview_geometry": None,
                "warm_field_transition_is_continuous": None,
                "cool_field_transition_is_continuous": None,
                "neutral_ramp_is_monotonic": None,
                "native_blocks_are_uniform": None,
                "edge_features_1_2_4_8px_resolved": [None, None, None, None],
                "left_right_halves_match": None,
                "operator_words": None,
            },
            "capture": {
                "fixed_camera_position": None,
                "fixed_exposure": None,
                "fixed_white_balance": None,
                "fixed_focus": None,
                "fixed_light_source": None,
                "near_and_mid_distance_records_present": None,
            },
            "supervision": {
                "electrical_normal": None,
                "temperature_c": None,
                "esp32_did_not_restart": None,
                "each_following_white_recovery_clean": None,
            },
            "interpretation": {
                "spatial_mixing_only": True,
                "single_pixel_new_state_claimed": False,
                "runtime_lut_or_waveform_change_claimed": False,
                "nominal_preview_is_colorimetric_prediction": False,
                "measured_color_claimed": False,
            },
            "automatic_next_action_authorized": False,
            "retry_authorized": False,
            "recovery_authorized": False,
        }
    )


def _operator_card() -> bytes:
    lines = [
        "# MF1750 factory-OTP dither effects extension operator card",
        "",
        "This extension evaluates spatial mixing only. It does not add a",
        "single-pixel pigment state and does not change a LUT or waveform.",
        "",
        "The existing frozen dither block atlas remains the first pair:",
        "",
        "1. ratio block atlas",
        "2. factory-OTP white recovery",
        "",
        "If that pair already has a committed result and clean-white",
        "finalization, do not replay it. The extension adds exactly two pairs:",
        "",
        "3. seven pairwise 8x8-ordered gradients",
        "4. factory-OTP white recovery",
        "5. effects chart: two three-colour fields, neutral ramp, native blocks,",
        "   and 1/2/4/8-pixel edge strip",
        "6. factory-OTP white recovery",
        "",
        "Both controller halves repeat the same layout and mask phase. Compare",
        "left/right before interpreting colour or banding.",
        "",
        "Record each target from 20-30 cm and about 1 m with fixed camera",
        "position, exposure, white balance, focus, and light. The strict PNG",
        "uses nominal RGB only and is not a prediction of measured panel colour.",
        "",
        "Every visible target and every white recovery is a separate action.",
        "Each requires J2-OFF app-only flash/verify, same-boot read-only",
        "diagnostic, fresh electrical/temperature gate, exact authorization,",
        "permanent claim, one action, J2 disconnect, and finalization.",
        "",
        "Stop without retry or automatic recovery on identity, boot, current,",
        "temperature, BUSY, result durability, left/right, or white-cleanliness",
        "failure. This card authorizes no live action.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _bundle_payloads() -> dict[str, bytes]:
    return {
        "pair-gradients.frame.bin": suite.build_frame(suite.ROLE_PAIR_GRADIENTS),
        "effects-chart.frame.bin": suite.build_frame(suite.ROLE_EFFECTS_CHART),
        "white.frame.bin": suite.build_frame(suite.ROLE_WHITE),
        "pair-gradients-strict-preview.png": _strict_preview(suite.ROLE_PAIR_GRADIENTS),
        "effects-chart-strict-preview.png": _strict_preview(suite.ROLE_EFFECTS_CHART),
        "layout.json": _canonical(suite.layout_manifest()),
        "operator-observation-template.json": _canonical(_observation_template()),
        "operator-card.md": _operator_card(),
    }


def _bundle_manifest(payloads: Mapping[str, bytes]) -> dict[str, Any]:
    unsigned = {
        "schema_version": 1,
        "kind": BUNDLE_KIND,
        "classification": suite.CLASSIFICATION,
        "offline_only": True,
        "device_io_performed": False,
        "network_io_performed": False,
        "visible_refresh_authorized": False,
        "profile_source": suite.PROFILE_SOURCE,
        "runtime_lut_or_waveform_changed": False,
        "spatial_mixing_only": True,
        "new_target_frame_count": 2,
        "new_white_recovery_frame_count": 1,
        "planned_new_visible_actions": 4,
        "extends_existing_block_atlas_pair_without_modifying_it": True,
        "layout_canonical_sha256": suite.layout_manifest()["integrity"][
            "canonical_sha256"
        ],
        "files": {
            name: {"bytes": len(payload), "sha256": _sha256(payload)}
            for name, payload in sorted(payloads.items())
        },
    }
    return _seal(unsigned)


def build_bundle(output_dir: Path) -> dict[str, Any]:
    payloads = _bundle_payloads()
    manifest = _bundle_manifest(payloads)
    directory = _create_directory(output_dir)
    for name, payload in payloads.items():
        _write_new(directory / name, payload)
    _write_new(directory / "bundle-manifest.json", _canonical(manifest))
    return validate_bundle(directory)


def validate_bundle(bundle_dir: Path) -> dict[str, Any]:
    try:
        metadata = bundle_dir.lstat()
        directory = bundle_dir.resolve(strict=True)
    except OSError as error:
        raise DitherEffectsBundleError(
            f"bundle directory cannot be resolved: {error}"
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise DitherEffectsBundleError("bundle must be a non-symlink directory")
    found = {entry.name for entry in directory.iterdir()}
    if found != EXPECTED_FILES:
        raise DitherEffectsBundleError("bundle file set differs from the contract")

    expected_payloads = _bundle_payloads()
    for name, expected in expected_payloads.items():
        actual = _read_regular(directory / name, label=name)
        if actual != expected:
            raise DitherEffectsBundleError(
                f"{name} differs from deterministic regeneration"
            )

    manifest_payload = _read_regular(
        directory / "bundle-manifest.json", label="bundle manifest"
    )
    manifest = _strict_json(manifest_payload, label="bundle manifest")
    _validate_seal(manifest, label="bundle manifest")
    expected_manifest = _bundle_manifest(expected_payloads)
    if dict(manifest) != expected_manifest:
        raise DitherEffectsBundleError("bundle manifest differs")
    return {
        "bundle": str(directory),
        "file_count": len(found),
        "manifest_bytes": len(manifest_payload),
        "manifest_file_sha256": _sha256(manifest_payload),
        "manifest_canonical_sha256": manifest["integrity"]["canonical_sha256"],
        "layout_canonical_sha256": manifest["layout_canonical_sha256"],
        "pair_gradients_frame_sha256": suite.frame_identity(
            suite.ROLE_PAIR_GRADIENTS
        ).frame.sha256,
        "effects_chart_frame_sha256": suite.frame_identity(
            suite.ROLE_EFFECTS_CHART
        ).frame.sha256,
        "white_frame_sha256": suite.frame_identity(suite.ROLE_WHITE).frame.sha256,
        "hardware_tested": False,
        "device_io_performed": False,
        "network_io_performed": False,
        "visible_refresh_authorized": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", allow_abbrev=False)
    build.add_argument("--output-dir", type=Path, required=True)
    validate = commands.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--bundle-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "build":
            output = build_bundle(args.output_dir)
        else:
            output = validate_bundle(args.bundle_dir)
    except DitherEffectsBundleError as error:
        print(f"EC5 dither effects error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
