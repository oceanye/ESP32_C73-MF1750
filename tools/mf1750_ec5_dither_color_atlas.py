#!/usr/bin/env python3
"""Build or deep-validate the offline EC5 rectangular dither-colour atlas."""

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

from host import dither_color_atlas as atlas  # noqa: E402
from host.color_pipeline.preview import encode_rgb_png  # noqa: E402
from host.epd_frame import HEIGHT, WIDTH, unpack_pixels  # noqa: E402


BUNDLE_KIND = "mf1750-ec5-dither-color-atlas-offline-bundle"
OBSERVATION_TEMPLATE_KIND = "mf1750-ec5-dither-color-atlas-observation-template"
MAX_FILE_BYTES = 16 * 1024 * 1024
EXPECTED_FILES = frozenset(
    {
        "atlas.frame.bin",
        "white.frame.bin",
        "strict-preview.png",
        "layout.json",
        "operator-observation-template.json",
        "operator-card.md",
        "bundle-manifest.json",
    }
)

DEVICE_RGB = {
    0: (0, 0, 0),
    1: (255, 255, 255),
    2: (255, 255, 0),
    3: (255, 0, 0),
    5: (0, 0, 255),
    6: (0, 255, 0),
}


class DitherAtlasToolError(RuntimeError):
    """The atlas bundle is incomplete, inconsistent, or unsafe to create."""


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
        raise DitherAtlasToolError(f"value is not canonical JSON: {error}") from error


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
                raise DitherAtlasToolError(f"{label} contains duplicate key {key!r}")
            result[key] = value
        return result

    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicate,
            parse_constant=lambda token: (_ for _ in ()).throw(
                DitherAtlasToolError(f"{label} contains forbidden {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DitherAtlasToolError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(root, Mapping):
        raise DitherAtlasToolError(f"{label} root must be an object")
    return root


def _validate_seal(root: Mapping[str, Any], *, label: str) -> None:
    integrity = root.get("integrity")
    if not isinstance(integrity, Mapping) or set(integrity) != {
        "canonical_sha256",
        "scope",
    }:
        raise DitherAtlasToolError(f"{label} integrity fields differ")
    unsigned = dict(root)
    unsigned.pop("integrity")
    expected = {
        "canonical_sha256": _sha256(_canonical(unsigned)),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    if dict(integrity) != expected:
        raise DitherAtlasToolError(f"{label} integrity differs")


def _read_regular(path: Path, *, label: str) -> bytes:
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise DitherAtlasToolError(f"{label} must be a regular non-symlink file")
        if not 0 < before.st_size <= MAX_FILE_BYTES:
            raise DitherAtlasToolError(f"{label} size is invalid")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise DitherAtlasToolError(f"could not read {label}: {error}") from error
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise DitherAtlasToolError(f"{label} changed while read")
    if len(payload) != after.st_size:
        raise DitherAtlasToolError(f"{label} read length differs")
    return payload


def _write_new(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise DitherAtlasToolError(f"refusing to overwrite {path}") from error
    except OSError as error:
        raise DitherAtlasToolError(f"could not write {path}: {error}") from error


def _create_directory(path: Path) -> Path:
    if os.path.lexists(path):
        raise DitherAtlasToolError("output directory already exists")
    try:
        parent_meta = path.parent.lstat()
        parent = path.parent.resolve(strict=True)
        if stat.S_ISLNK(parent_meta.st_mode) or not stat.S_ISDIR(parent_meta.st_mode):
            raise DitherAtlasToolError("output parent must be a non-symlink directory")
        directory = parent / path.name
        directory.mkdir()
        metadata = directory.lstat()
    except OSError as error:
        raise DitherAtlasToolError(
            f"could not create output directory: {error}"
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise DitherAtlasToolError("created output is not a regular directory")
    return directory


def _strict_preview() -> bytes:
    codes = unpack_pixels(atlas.build_frame("atlas"))
    rgb = bytearray(len(codes) * 3)
    for index, code in enumerate(codes):
        color = DEVICE_RGB[code]
        target = index * 3
        rgb[target : target + 3] = bytes(color)
    return encode_rgb_png(WIDTH, HEIGHT, rgb)


def _observation_template() -> dict[str, Any]:
    rows = []
    for row, family in enumerate(atlas.MIX_FAMILIES):
        rows.append(
            {
                "display_row": row,
                "row_id": family.row_id,
                "appearance_hypothesis": family.appearance_hypothesis,
                "native_pair": [family.color_a, family.color_b],
                "near_view_20_to_30_cm": {
                    "pattern_visible_by_column": [None, None, None, None, None],
                    "middle_patch_looks_like_distinct_hue": None,
                    "operator_words": None,
                },
                "mid_view_about_1_m": {
                    "three_mixed_columns_are_visually_ordered": None,
                    "middle_patch_looks_like_distinct_hue": None,
                    "operator_words": None,
                },
                "left_right_halves_match": None,
            }
        )
    return _seal(
        {
            "schema_version": 1,
            "kind": OBSERVATION_TEMPLATE_KIND,
            "layout_canonical_sha256": atlas.layout_manifest()["integrity"][
                "canonical_sha256"
            ],
            "not_a_completed_observation": True,
            "screen": {
                "matches_strict_preview": None,
                "white_gaps_and_edges_clean": None,
                "unexpected_residual": None,
                "left_right_global_match": None,
            },
            "rows": rows,
            "supervision": {
                "electrical_normal": None,
                "temperature_c": None,
                "esp32_did_not_restart": None,
            },
            "interpretation": {
                "spatial_mixing_only": True,
                "single_pixel_new_state_claimed": False,
                "runtime_lut_or_waveform_change_claimed": False,
                "measured_color_claimed": False,
            },
            "automatic_next_action_authorized": False,
            "retry_authorized": False,
            "recovery_authorized": False,
        }
    )


def _operator_card() -> bytes:
    lines = [
        "# EC5 dither colour atlas operator card",
        "",
        "This is spatial mixing of native factory-OTP pixels, not a new per-pixel state.",
        "",
        "Both controller halves repeat the same 7 x 5 grid. Columns are:",
        "",
        "`pure A | 75% A + 25% B | 50/50 checkerboard | 25% A + 75% B | pure B`",
        "",
        "| Row | Native pair A+B | Appearance hypothesis |",
        "|---:|---|---|",
    ]
    for index, family in enumerate(atlas.MIX_FAMILIES, 1):
        lines.append(
            f"| {index} | {family.color_a} + {family.color_b} | "
            f"{family.appearance_hypothesis} |"
        )
    lines.extend(
        [
            "",
            "For every row, compare the three mixed patches with both pure endpoints.",
            "Record near view (20-30 cm) and mid view (about 1 m) separately.",
            "Use your own colour words; the hypothesis column is not a required verdict.",
            "Confirm both halves match, gaps/edges are clean, electrical state is normal,",
            "temperature is recorded, and the ESP32 did not restart.",
            "",
            "No next action, retry, or white recovery is authorized by this card.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def _bundle_payloads() -> dict[str, bytes]:
    return {
        "atlas.frame.bin": atlas.build_frame("atlas"),
        "white.frame.bin": atlas.build_frame("white"),
        "strict-preview.png": _strict_preview(),
        "layout.json": _canonical(atlas.layout_manifest()),
        "operator-observation-template.json": _canonical(_observation_template()),
        "operator-card.md": _operator_card(),
    }


def _bundle_manifest(payloads: Mapping[str, bytes]) -> dict[str, Any]:
    unsigned = {
        "schema_version": 1,
        "kind": BUNDLE_KIND,
        "classification": atlas.CLASSIFICATION,
        "offline_only": True,
        "device_io_performed": False,
        "network_io_performed": False,
        "visible_refresh_authorized": False,
        "profile_source": atlas.PROFILE_SOURCE,
        "runtime_lut_or_waveform_changed": False,
        "spatial_mixing_only": True,
        "layout_canonical_sha256": atlas.layout_manifest()["integrity"][
            "canonical_sha256"
        ],
        "source_references": [
            {
                "role": "experiment_description",
                "url": "https://myembeddedstuff.com/e-ink-spectra-6-color",
                "adopted_fact": "one-pixel 50/50 checkerboard and seven native-colour pairs",
                "source_code_claimed": False,
            },
            {
                "role": "secondary_summary",
                "url": "https://blog.adafruit.com/2026/01/05/beyond-6-colors-exploring-dithering-on-spectra-6-color-e-ink-displays/",
                "adopted_fact": "summary of the same spatial-dither experiment",
                "source_code_claimed": False,
            },
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
        raise DitherAtlasToolError(
            f"bundle directory cannot be resolved: {error}"
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise DitherAtlasToolError("bundle must be a non-symlink directory")
    found = {entry.name for entry in directory.iterdir()}
    if found != EXPECTED_FILES:
        raise DitherAtlasToolError("bundle file set differs from the contract")

    expected_payloads = _bundle_payloads()
    actual_payloads: dict[str, bytes] = {}
    for name, expected in expected_payloads.items():
        actual = _read_regular(directory / name, label=name)
        if actual != expected:
            raise DitherAtlasToolError(
                f"{name} differs from deterministic regeneration"
            )
        actual_payloads[name] = actual

    manifest_payload = _read_regular(
        directory / "bundle-manifest.json", label="bundle manifest"
    )
    manifest = _strict_json(manifest_payload, label="bundle manifest")
    _validate_seal(manifest, label="bundle manifest")
    expected_manifest = _bundle_manifest(expected_payloads)
    if dict(manifest) != expected_manifest:
        raise DitherAtlasToolError("bundle manifest differs")
    return {
        "bundle": str(directory),
        "file_count": len(found),
        "manifest_bytes": len(manifest_payload),
        "manifest_file_sha256": _sha256(manifest_payload),
        "manifest_canonical_sha256": manifest["integrity"]["canonical_sha256"],
        "atlas_frame_sha256": atlas.frame_identity("atlas").frame.sha256,
        "cs1_dtm_sha256": atlas.frame_identity("atlas").cs1_dtm.sha256,
        "cs2_dtm_sha256": atlas.frame_identity("atlas").cs2_dtm.sha256,
        "roi_count": len(atlas.atlas_rois()),
        "hardware_tested": False,
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
    except DitherAtlasToolError as error:
        print(f"EC5 dither atlas error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
