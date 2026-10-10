#!/usr/bin/env python3
"""Build the implementation-complete, still non-live dither fallback V2 gate."""

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
from tools import mf1750_ec5_dither_effects_extension_campaign as extension_campaign  # noqa: E402
from tools import mf1750_ec5_dither_effects_extension_contract as extension_contract  # noqa: E402
from tools import mf1750_ec5_dither_effects_suite as extension_bundle  # noqa: E402


SCHEMA_VERSION = 2
KIND = "mf1750-ec5-factory-otp-dither-fallback-readiness"
MAX_FILE_BYTES = 32_000_000
DEFAULT_ATLAS_RELEASE = (
    REPO_ROOT / ".test-output/hardware/"
    "MF1750_EC5_DITHER_COLOR_ATLAS_RELEASE_OFFLINE_20260810_V1/"
    "dither-color-atlas-real-release.json"
)
DEFAULT_EXTENSION_BUNDLE = (
    REPO_ROOT / ".test-output/offline/"
    "MF1750_EC5_DITHER_EFFECTS_EXTENSION_OFFLINE_20260817_V1"
)
DEFAULT_STAGED_RELEASE = (
    REPO_ROOT / ".test-output/offline/"
    "MF1750_EC5_DITHER_EFFECTS_EXTENSION_STAGED_RELEASE_20260818_V2/"
    "dither-effects-extension-staged-release.json"
)
IMPLEMENTATION_FILES = (
    "host/dither_effects_suite.py",
    "src/epd_driver.cpp",
    "src/epd_driver.h",
    "src/ec5_dither_effects_extension_main.cpp",
    "src/ec5_dither_effects_extension_epd_driver.cpp",
    "src/ec5_dither_effects_extension_epd_driver.h",
    "src/ec5_dither_effects_extension_driver.inc",
    "platformio.dither_effects_extension.ini",
    "tools/mf1750_ec5_dither_effects_extension_contract.py",
    "tools/mf1750_ec5_dither_effects_extension_compiled_identity.py",
    "tools/mf1750_ec5_dither_effects_extension_campaign.py",
    "tools/mf1750_ec5_dither_effects_extension_physical_once.py",
)


class DitherFallbackReadinessV2Error(RuntimeError):
    """A bound fallback artifact or deterministic readiness field differed."""


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
        raise DitherFallbackReadinessV2Error(str(error)) from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read(path: Path, *, label: str, maximum: int = MAX_FILE_BYTES) -> bytes:
    candidate = Path(path)
    try:
        before = candidate.lstat()
        resolved = candidate.resolve(strict=True)
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise DitherFallbackReadinessV2Error(
                f"{label} must be a regular non-symlink file"
            )
        if not 0 < before.st_size <= maximum:
            raise DitherFallbackReadinessV2Error(f"{label} size is invalid")
        payload = resolved.read_bytes()
        after = resolved.lstat()
    except OSError as error:
        raise DitherFallbackReadinessV2Error(
            f"could not read {label}: {error}"
        ) from error
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise DitherFallbackReadinessV2Error(f"{label} changed while read")
    if len(payload) != after.st_size:
        raise DitherFallbackReadinessV2Error(f"{label} read length differs")
    return payload


def _strict_decode(payload: bytes, *, label: str) -> Mapping[str, Any]:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise DitherFallbackReadinessV2Error(
                    f"{label} contains duplicate key {key!r}"
                )
            result[key] = value
        return result

    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                DitherFallbackReadinessV2Error(f"{label} contains forbidden {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DitherFallbackReadinessV2Error(f"{label} is invalid JSON") from error
    if not isinstance(root, Mapping):
        raise DitherFallbackReadinessV2Error(f"{label} root must be an object")
    return root


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    root = deepcopy(dict(unsigned))
    root["readiness_id"] = _sha256(_canonical(unsigned))
    sealed = deepcopy(root)
    sealed["integrity"] = {
        "canonical_sha256": _sha256(_canonical(root)),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    return sealed


def _implementation_bindings() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in IMPLEMENTATION_FILES:
        path = REPO_ROOT / relative
        payload = _read(path, label=relative)
        rows.append(
            {
                "relative_file": relative,
                "bytes": len(payload),
                "sha256": _sha256(payload),
            }
        )
    return rows


def _sequence() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, descriptor in enumerate(atlas_contract.DESCRIPTORS, start=1):
        rows.append(
            {
                "fallback_ordinal": index,
                "source_branch": "EXISTING_FROZEN_BLOCK_ATLAS_PAIR",
                "source_action_ordinal": descriptor["ordinal"],
                "role": descriptor["role"],
                "hardware_action_id": descriptor["hardware_action_id"],
                "frame_sha256": descriptor["frame_sha256"],
                "is_target": descriptor["role"] == atlas_contract.ROLE_ATLAS,
                "is_white_recovery": descriptor["role"] == atlas_contract.ROLE_WHITE,
                "already_in_ten_action_core_screening": True,
                "transport_surface": "fixed-compiled bodyless /arm then /execute",
                "current_execution_release_present": True,
                "current_live_authorized": False,
            }
        )
    for index, descriptor in enumerate(extension_contract.DESCRIPTORS, start=3):
        role = str(descriptor["role"])
        rows.append(
            {
                "fallback_ordinal": index,
                "source_branch": "NEW_FIXED_COMPILED_DITHER_EFFECTS_EXTENSION",
                "source_action_ordinal": descriptor["ordinal"],
                "role": role,
                "hardware_action_id": descriptor["hardware_action_id"],
                "frame_sha256": descriptor["frame_sha256"],
                "is_target": role
                in (
                    extension_contract.ROLE_PAIR_GRADIENTS,
                    extension_contract.ROLE_EFFECTS_CHART,
                ),
                "is_white_recovery": role
                in (
                    extension_contract.ROLE_WHITE_AFTER_GRADIENTS,
                    extension_contract.ROLE_WHITE_AFTER_EFFECTS,
                ),
                "already_in_ten_action_core_screening": False,
                "transport_surface": "fixed-compiled bodyless /arm then /execute",
                "current_execution_release_present": False,
                "current_staged_release_present": True,
                "current_live_authorized": False,
            }
        )
    return rows


def build_readiness(
    *,
    atlas_release_file: Path = DEFAULT_ATLAS_RELEASE,
    extension_bundle_dir: Path = DEFAULT_EXTENSION_BUNDLE,
    staged_release_file: Path = DEFAULT_STAGED_RELEASE,
) -> dict[str, Any]:
    try:
        atlas = atlas_campaign.validate_materialized_release(atlas_release_file)
        bundle = extension_bundle.validate_bundle(extension_bundle_dir)
        staged = extension_campaign.validate_staged_release(staged_release_file)
    except (
        atlas_campaign.DitherColorAtlasCampaignError,
        extension_bundle.DitherEffectsBundleError,
        extension_campaign.DitherEffectsExtensionCampaignError,
    ) as error:
        raise DitherFallbackReadinessV2Error(str(error)) from error
    if (
        staged["predecessor_action_id"]
        != atlas_contract.DESCRIPTORS[1]["hardware_action_id"]
    ):
        raise DitherFallbackReadinessV2Error(
            "extension predecessor does not bind core action 10"
        )
    actions = _sequence()
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "classification": (
                "FACTORY_OTP_SPATIAL_DITHER_FALLBACK_IMPLEMENTATION_COMPLETE_NON_LIVE"
            ),
            "existing_block_atlas_release": dict(atlas),
            "extension_bundle": dict(bundle),
            "extension_staged_release": dict(staged),
            "extension_contract_id": extension_contract.campaign_manifest()[
                "contract_id"
            ],
            "implementation_bindings": _implementation_bindings(),
            "action_sequence": actions,
            "counts": {
                "full_fallback_visible_actions": 6,
                "full_fallback_targets": 3,
                "full_fallback_white_recoveries": 3,
                "already_in_ten_action_core_screening": 2,
                "additional_visible_actions_after_completed_core_screening": 4,
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
                "may_be_autoappended_to_core": False,
                "separate_optional_window_requires_fresh_gate": True,
            },
            "readiness": {
                "test_frames_previews_and_observation_template_ready": True,
                "existing_block_pair_execution_release_ready": True,
                "extension_fixed_compiled_firmware_ready": True,
                "extension_linked_identity_gate_passed": True,
                "dedicated_extension_adapter_ready": True,
                "extension_staged_release_ready": True,
                "all_current_offline_implementation_work_complete": True,
                "future_core_action_10_white_evidence_available": False,
                "extension_execution_release_ready": False,
                "full_live_execution_chain_ready": False,
                "execution_gate_reached": False,
                "live_authorized": False,
            },
            "future_event_gate": [
                "complete_and_finalize_core_action_9_ratio_block_atlas",
                "complete_and_finalize_core_action_10_factory_otp_clean_white",
                "run_offline_finalize_real_against_exact_action_10_result_observation_claim",
                "separately_choose_optional_dither_window_at_clean_white_safe_stop",
                "j2_off_app_only_flash_writeback_hash_and_same_boot_diagnostic",
                "fresh_operator_state_and_exact_per_action_authorization",
            ],
            "interpretation": {
                "spatial_mixing_only": True,
                "new_single_pixel_physical_colour_claimed": False,
                "runtime_waveform_or_lut_changed": False,
                "nominal_preview_is_colorimetric_prediction": False,
            },
            "device_io_performed": False,
            "network_io_performed": False,
            "serial_io_performed": False,
            "firmware_upload_performed": False,
            "visible_refreshes": 0,
        }
    )


def validate_readiness(root: Mapping[str, Any]) -> dict[str, Any]:
    integrity = root.get("integrity")
    if not isinstance(integrity, Mapping):
        raise DitherFallbackReadinessV2Error("readiness integrity is absent")
    unsigned_with_id = dict(root)
    unsigned_with_id.pop("integrity")
    expected_canonical = _sha256(_canonical(unsigned_with_id))
    if integrity != {
        "canonical_sha256": expected_canonical,
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }:
        raise DitherFallbackReadinessV2Error("readiness integrity differs")
    readiness_id = unsigned_with_id.pop("readiness_id", None)
    if readiness_id != _sha256(_canonical(unsigned_with_id)):
        raise DitherFallbackReadinessV2Error("readiness ID differs")
    atlas = root.get("existing_block_atlas_release")
    bundle = root.get("extension_bundle")
    staged = root.get("extension_staged_release")
    if not all(isinstance(value, Mapping) for value in (atlas, bundle, staged)):
        raise DitherFallbackReadinessV2Error("readiness references are absent")
    rebuilt = build_readiness(
        atlas_release_file=Path(str(atlas["file"])),
        extension_bundle_dir=Path(str(bundle["bundle"])),
        staged_release_file=Path(str(staged["file"])),
    )
    if dict(root) != rebuilt:
        raise DitherFallbackReadinessV2Error(
            "readiness differs from deterministic reconstruction"
        )
    return {
        "valid": True,
        "readiness_id": root["readiness_id"],
        "canonical_sha256": root["integrity"]["canonical_sha256"],
        **dict(root["counts"]),
        **dict(root["readiness"]),
        "device_io_performed": False,
        "network_io_performed": False,
        "visible_refreshes": 0,
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
        raise DitherFallbackReadinessV2Error(f"refusing to overwrite {path}") from error
    except OSError as error:
        raise DitherFallbackReadinessV2Error(str(error)) from error
    return payload


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", allow_abbrev=False)
    build.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--readiness", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "build":
            root = build_readiness()
            payload = _write_new(args.output, root)
            output = {
                "file": str(args.output.resolve()),
                "bytes": len(payload),
                "file_sha256": _sha256(payload),
                **validate_readiness(root),
            }
        else:
            payload = _read(args.readiness, label="dither fallback readiness")
            root = _strict_decode(payload, label="dither fallback readiness")
            output = {
                "file": str(args.readiness.resolve()),
                "bytes": len(payload),
                "file_sha256": _sha256(payload),
                **validate_readiness(root),
            }
    except DitherFallbackReadinessV2Error as error:
        print(f"EC5 dither fallback V2 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
