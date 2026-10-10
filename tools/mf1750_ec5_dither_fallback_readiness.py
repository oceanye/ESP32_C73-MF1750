#!/usr/bin/env python3
"""Compile/validate the non-live six-action MF1750 dither fallback plan."""

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

from tools import mf1750_ec5_dither_color_atlas_campaign as atlas_campaign  # noqa: E402
from tools import mf1750_ec5_dither_color_atlas_contract as atlas_contract  # noqa: E402
from tools import mf1750_ec5_dither_effects_fixed_action_contract as extension_contract  # noqa: E402
from tools import mf1750_ec5_dither_effects_suite as extension_bundle  # noqa: E402


SCHEMA_VERSION = 1
KIND = "mf1750-ec5-factory-otp-dither-fallback-readiness"
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_FIRMWARE_BYTES = 4 * 1024 * 1024

DEFAULT_ATLAS_RELEASE = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_DITHER_COLOR_ATLAS_RELEASE_OFFLINE_20260810_V1"
    / "dither-color-atlas-real-release.json"
)
DEFAULT_EXTENSION_BUNDLE = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "MF1750_EC5_DITHER_EFFECTS_EXTENSION_OFFLINE_20260817_V1"
)
DEFAULT_RC2G_FIRMWARE = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "RC2G_N2_PHYSICAL_SESSION_20260808_2132"
    / "q1-target-result"
    / "FIRMWARE.bin"
)


class DitherFallbackReadinessError(RuntimeError):
    """The fallback plan or one of its immutable inputs failed closed."""


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
        raise DitherFallbackReadinessError(
            f"value is not canonical JSON: {error}"
        ) from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DitherFallbackReadinessError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _decode(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                DitherFallbackReadinessError(f"{label} contains forbidden {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DitherFallbackReadinessError(
            f"{label} is invalid JSON: {error}"
        ) from error
    if not isinstance(root, Mapping):
        raise DitherFallbackReadinessError(f"{label} root must be an object")
    return root


def _read_regular(path: Path, *, label: str, maximum: int) -> bytes:
    candidate = Path(path)
    try:
        before = candidate.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise DitherFallbackReadinessError(
                f"{label} must be a regular non-symlink file"
            )
        if not 0 < before.st_size <= maximum:
            raise DitherFallbackReadinessError(f"{label} size is invalid")
        payload = candidate.read_bytes()
        after = candidate.lstat()
    except OSError as error:
        raise DitherFallbackReadinessError(
            f"could not read {label}: {error}"
        ) from error
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise DitherFallbackReadinessError(f"{label} changed while read")
    if len(payload) != after.st_size:
        raise DitherFallbackReadinessError(f"{label} read length differs")
    return payload


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(unsigned))
    result["readiness_id"] = _sha256(_canonical(unsigned))
    sealed = deepcopy(result)
    sealed["integrity"] = {
        "canonical_sha256": _sha256(_canonical(result)),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    return sealed


def _validate_seal(root: Mapping[str, Any]) -> None:
    integrity = root.get("integrity")
    if not isinstance(integrity, Mapping) or set(integrity) != {
        "canonical_sha256",
        "scope",
    }:
        raise DitherFallbackReadinessError("readiness integrity fields differ")
    without_integrity = dict(root)
    without_integrity.pop("integrity")
    expected_integrity = {
        "canonical_sha256": _sha256(_canonical(without_integrity)),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    if dict(integrity) != expected_integrity:
        raise DitherFallbackReadinessError("readiness integrity differs")
    readiness_id = without_integrity.pop("readiness_id", None)
    if readiness_id != _sha256(_canonical(without_integrity)):
        raise DitherFallbackReadinessError("readiness ID differs")


def _atlas_actions() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ordinal, descriptor in enumerate(atlas_contract.DESCRIPTORS, start=1):
        rows.append(
            {
                "fallback_ordinal": ordinal,
                "source_branch": "EXISTING_FROZEN_BLOCK_ATLAS_PAIR",
                "source_action_ordinal": descriptor["ordinal"],
                "role": descriptor["role"],
                "hardware_action_id": descriptor["hardware_action_id"],
                "frame_sha256": descriptor["frame_sha256"],
                "visible_semantics": descriptor["branch"],
                "is_target": descriptor["role"] == atlas_contract.ROLE_ATLAS,
                "is_white_recovery": descriptor["role"] == atlas_contract.ROLE_WHITE,
                "already_in_ten_action_core_screening": True,
                "transport_surface": "fixed-compiled /arm then /execute",
                "maximum_visible_refreshes": 1,
                "separate_fresh_gate": True,
                "separate_permanent_claim": True,
                "automatic_retry": False,
                "automatic_recovery": False,
                "automatic_chaining": False,
                "current_execution_release_present": True,
                "current_live_authorized": False,
            }
        )
    return rows


def _extension_actions() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, descriptor in enumerate(extension_contract.DESCRIPTORS, start=3):
        rows.append(
            {
                "fallback_ordinal": index,
                "source_branch": "NEW_DITHER_EFFECTS_EXTENSION",
                "source_action_ordinal": descriptor["ordinal"],
                "role": descriptor["role"],
                "hardware_action_id": descriptor["hardware_action_id"],
                "frame_sha256": descriptor["frame"]["sha256"],
                "visible_semantics": descriptor["frame_role"],
                "is_target": not descriptor["recovery_action"],
                "is_white_recovery": descriptor["recovery_action"],
                "already_in_ten_action_core_screening": False,
                "transport_surface": "candidate fixed /api/frame adapter",
                "maximum_visible_refreshes": 1,
                "separate_fresh_gate": True,
                "separate_permanent_claim": True,
                "automatic_retry": False,
                "automatic_recovery": False,
                "automatic_chaining": False,
                "current_execution_release_present": False,
                "current_live_authorized": False,
            }
        )
    return rows


def build_readiness(
    *,
    atlas_release_file: Path = DEFAULT_ATLAS_RELEASE,
    extension_bundle_dir: Path = DEFAULT_EXTENSION_BUNDLE,
    rc2g_firmware_file: Path = DEFAULT_RC2G_FIRMWARE,
) -> dict[str, Any]:
    try:
        atlas = atlas_campaign.validate_materialized_release(atlas_release_file)
        extension = extension_bundle.validate_bundle(extension_bundle_dir)
    except (
        atlas_campaign.DitherColorAtlasCampaignError,
        extension_bundle.DitherEffectsBundleError,
    ) as error:
        raise DitherFallbackReadinessError(str(error)) from error

    firmware = _read_regular(
        rc2g_firmware_file,
        label="RC2G transport-candidate firmware",
        maximum=MAX_FIRMWARE_BYTES,
    )
    if (
        len(firmware) != extension_contract.TRANSPORT_FIRMWARE_BYTES
        or _sha256(firmware) != extension_contract.TRANSPORT_FIRMWARE_SHA256
    ):
        raise DitherFallbackReadinessError(
            "RC2G transport-candidate firmware identity differs"
        )
    if (
        extension["manifest_file_sha256"]
        != extension_contract.SOURCE_BUNDLE_MANIFEST_FILE_SHA256
        or extension["manifest_canonical_sha256"]
        != extension_contract.SOURCE_BUNDLE_MANIFEST_CANONICAL_SHA256
    ):
        raise DitherFallbackReadinessError(
            "dither extension bundle identity differs from action contract"
        )

    actions = _atlas_actions() + _extension_actions()
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "classification": ("FACTORY_OTP_SPATIAL_DITHER_FALLBACK_NON_LIVE_READINESS"),
        "existing_block_atlas_release": dict(atlas),
        "extension_bundle": dict(extension),
        "extension_action_contract": extension_contract.contract_manifest(),
        "transport_candidate": {
            "file": str(Path(rc2g_firmware_file).resolve()),
            "bytes": len(firmware),
            "sha256": _sha256(firmware),
            "build_tag": extension_contract.TRANSPORT_BUILD_TAG,
            "driver_api": extension_contract.TRANSPORT_DRIVER_API,
            "historically_hardware_proven": True,
            "dedicated_extension_adapter_materialized": False,
        },
        "action_sequence": actions,
        "counts": {
            "full_fallback_visible_actions": len(actions),
            "full_fallback_targets": sum(row["is_target"] for row in actions),
            "full_fallback_white_recoveries": sum(
                row["is_white_recovery"] for row in actions
            ),
            "already_in_ten_action_core_screening": sum(
                row["already_in_ten_action_core_screening"] for row in actions
            ),
            "additional_visible_actions_after_completed_core_screening": sum(
                not row["already_in_ten_action_core_screening"] for row in actions
            ),
        },
        "schedule": {
            "full_sequence": [
                "ratio-block-atlas",
                "white-after-ratio-blocks",
                "pair-gradients",
                "white-after-pair-gradients",
                "effects-chart",
                "white-after-effects-chart",
            ],
            "safe_stop_ordinals": [2, 4, 6],
            "if_core_actions_9_and_10_are_committed_pass_start_at": 3,
            "do_not_replay_committed_block_pair": True,
            "may_be_scheduled_after_core_as_separate_optional_window": True,
            "may_be_autoappended_to_core": False,
        },
        "interpretation": {
            "spatial_mixing_only": True,
            "new_single_pixel_physical_colour_claimed": False,
            "runtime_waveform_or_lut_changed": False,
            "nominal_preview_is_colorimetric_prediction": False,
            "candidate_effect_requires_fixed_capture_and_optional_colorimetry": True,
        },
        "readiness": {
            "test_frames_previews_and_observation_template_ready": True,
            "existing_block_pair_execution_release_ready": True,
            "extension_action_identities_ready": True,
            "extension_transport_candidate_verified": True,
            "dedicated_extension_adapter_ready": False,
            "extension_execution_release_ready": False,
            "full_live_execution_chain_ready": False,
            "execution_gate_reached": False,
            "live_authorized": False,
        },
        "remaining_offline_gate": [
            "implement_and_redteam_dedicated_fixed-frame_adapter",
            "materialize_and_deep-validate_extension_execution_release",
        ],
        "device_io_performed": False,
        "network_io_performed": False,
        "firmware_upload_performed": False,
        "visible_refreshes": 0,
    }
    return _seal(unsigned)


def validate_readiness(root: Mapping[str, Any]) -> dict[str, Any]:
    _validate_seal(root)
    if root.get("schema_version") != SCHEMA_VERSION or root.get("kind") != KIND:
        raise DitherFallbackReadinessError("readiness schema/kind differs")
    candidate = root.get("transport_candidate")
    bundle = root.get("extension_bundle")
    atlas = root.get("existing_block_atlas_release")
    if not all(isinstance(value, Mapping) for value in (candidate, bundle, atlas)):
        raise DitherFallbackReadinessError("readiness source references are absent")
    rebuilt = build_readiness(
        atlas_release_file=Path(str(atlas["file"])),
        extension_bundle_dir=Path(str(bundle["bundle"])),
        rc2g_firmware_file=Path(str(candidate["file"])),
    )
    if dict(root) != rebuilt:
        raise DitherFallbackReadinessError(
            "readiness differs from deterministic deep reconstruction"
        )
    counts = root["counts"]
    readiness = root["readiness"]
    return {
        "valid": True,
        "readiness_id": root["readiness_id"],
        "canonical_sha256": root["integrity"]["canonical_sha256"],
        "full_fallback_visible_actions": counts["full_fallback_visible_actions"],
        "full_fallback_targets": counts["full_fallback_targets"],
        "full_fallback_white_recoveries": counts["full_fallback_white_recoveries"],
        "additional_visible_actions_after_core": counts[
            "additional_visible_actions_after_completed_core_screening"
        ],
        "test_assets_ready": readiness[
            "test_frames_previews_and_observation_template_ready"
        ],
        "full_live_execution_chain_ready": readiness["full_live_execution_chain_ready"],
        "execution_gate_reached": readiness["execution_gate_reached"],
        "live_authorized": readiness["live_authorized"],
        "device_io_performed": root["device_io_performed"],
        "network_io_performed": root["network_io_performed"],
        "visible_refreshes": root["visible_refreshes"],
    }


def _write_new(path: Path, root: Mapping[str, Any]) -> bytes:
    payload = _canonical(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise DitherFallbackReadinessError(f"refusing to overwrite {path}") from error
    except OSError as error:
        raise DitherFallbackReadinessError(
            f"could not write readiness: {error}"
        ) from error
    return payload


def _load(path: Path) -> Mapping[str, Any]:
    payload = _read_regular(
        path, label="dither fallback readiness", maximum=MAX_JSON_BYTES
    )
    return _decode(payload, label="dither fallback readiness")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("materialize", allow_abbrev=False)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--atlas-release", type=Path, default=DEFAULT_ATLAS_RELEASE)
    build.add_argument(
        "--extension-bundle", type=Path, default=DEFAULT_EXTENSION_BUNDLE
    )
    build.add_argument("--rc2g-firmware", type=Path, default=DEFAULT_RC2G_FIRMWARE)
    check = commands.add_parser("validate", allow_abbrev=False)
    check.add_argument("--readiness", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "materialize":
            root = build_readiness(
                atlas_release_file=args.atlas_release,
                extension_bundle_dir=args.extension_bundle,
                rc2g_firmware_file=args.rc2g_firmware,
            )
            payload = _write_new(args.output, root)
            report = validate_readiness(root)
            report["readiness_file"] = str(args.output.resolve())
            report["readiness_file_bytes"] = len(payload)
            report["readiness_file_sha256"] = _sha256(payload)
        else:
            report = validate_readiness(_load(args.readiness))
    except DitherFallbackReadinessError as error:
        print(f"dither fallback readiness error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
