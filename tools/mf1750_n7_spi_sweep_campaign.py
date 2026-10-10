#!/usr/bin/env python3
"""Compile and deep-validate the offline N7 fixed-frequency SPI sweep bundle.

This module has no device, network, authorization, or claim surface.  It only
freezes the one N7 diagnostic firmware binary and the five explicitly
allowlisted MAP_ORIENT_V1 actions used by the supervised once-runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence


SCHEMA_VERSION = 1
KIND = "mf1750-n7-spi-sweep-campaign"
CAMPAIGN_ID = "n7-map-orient-v1-fixed-spi-sweep-v1"
FIRMWARE_ENVIRONMENT = "esp32-s3-devkitc-1-n7-spi-sweep"
FIRMWARE_BUILD_TAG = (
    "MF1750_DRIVER_N7_SPI_SWEEP_R16_MAPHASH_JOBTRACE_BUSYEDGE_2026-08-07"
)
FIRMWARE_EXPECTED_BYTES = 775_536
FIRMWARE_EXPECTED_SHA256 = (
    "81e905d299a0011d2f9617621e20e3262baea42aa9a6360522618bbb2414cb66"
)
DRIVER_API_VERSION = "MF1750_R16_CASCADE_V3"
FIXTURE = "map-orient-v1"
JOB_ACTION = "map_orient_v1_sweep"
FRAME_BYTES = 307_200
EXPECTED_FULL_FNV1A = 0x9D04142D
EXPECTED_CS1_FNV1A = 0xF26832DD
EXPECTED_CS2_FNV1A = 0xFE199FF5
MINIMUM_PANEL_POWER_OFF_S = 10.0
FREQUENCIES = (1_000_000, 2_000_000, 4_000_000, 8_000_000, 10_000_000)
ROUTES = {
    1_000_000: "/api/diagnostic/map-orient-v1-sweep-1mhz",
    2_000_000: "/api/diagnostic/map-orient-v1-sweep-2mhz",
    4_000_000: "/api/diagnostic/map-orient-v1-sweep-4mhz",
    8_000_000: "/api/diagnostic/map-orient-v1-sweep-8mhz",
    10_000_000: "/api/diagnostic/map-orient-v1-sweep-10mhz",
}
DEFAULT_MAPPINGS = (
    {
        "controller": 1,
        "source_half": 0,
        "flip_x": False,
        "flip_y": False,
        "nibble_swap": False,
    },
    {
        "controller": 2,
        "source_half": 1,
        "flip_x": False,
        "flip_y": False,
        "nibble_swap": False,
    },
)
REQUIRED_FILES = frozenset({"campaign.json", "firmware.bin", "SHA256SUMS.txt"})


class N7CampaignError(ValueError):
    """Raised when an N7 campaign bundle is incomplete or has changed."""


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise N7CampaignError(f"campaign value is not canonical JSON: {error}") from error


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require_sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise N7CampaignError(f"{label} must be 64 lowercase hexadecimal digits")
    return value


def _action_template(index: int, frequency_hz: int) -> dict[str, Any]:
    label = f"{frequency_hz // 1_000_000}mhz"
    predecessor = (
        {
            "kind": "fresh-n7-firmware-boot",
            "expected_job_id": 0,
            "expected_operation_id": 0,
        }
        if index == 0
        else {
            "kind": "previous-frequency-pass-result",
            "frequency_hz": FREQUENCIES[index - 1],
            "esp32_reboot_forbidden": True,
        }
    )
    body = {
        "index": index,
        "action_id": f"n7-map-orient-v1-sweep-{label}-once-v1",
        "frequency_hz": frequency_hz,
        "method": "POST",
        "endpoint": ROUTES[frequency_hz],
        "request_body": "none",
        "query_or_form_arguments_allowed": False,
        "job_action": JOB_ACTION,
        "fixture": FIXTURE,
        "frame_fnv1a": EXPECTED_FULL_FNV1A,
        "predecessor": predecessor,
        "panel_power_cycle": {
            "j2_p1_off_before_action": True,
            "minimum_off_s": MINIMUM_PANEL_POWER_OFF_S,
            "esp32_must_remain_powered_after_first_action": index > 0,
        },
        "visible_action_count": 1,
        "maximum_visible_posts": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
        "higher_frequencies_blocked_unless_pass": True,
    }
    return {**body, "template_sha256": sha256(canonical_json(body))}


def build_campaign(firmware: bytes, *, created_at_utc: str) -> dict[str, Any]:
    if not isinstance(firmware, bytes) or not firmware:
        raise N7CampaignError("firmware must be non-empty bytes")
    if FIRMWARE_BUILD_TAG.encode("ascii") not in firmware:
        raise N7CampaignError("binary does not contain the fixed N7 firmware build tag")
    if len(firmware) != FIRMWARE_EXPECTED_BYTES or sha256(firmware) != FIRMWARE_EXPECTED_SHA256:
        raise N7CampaignError(
            "binary bytes/SHA-256 differ from the frozen N7 diagnostic firmware"
        )
    if not isinstance(created_at_utc, str) or not created_at_utc.endswith("Z"):
        raise N7CampaignError("created_at_utc must be an explicit UTC timestamp ending in Z")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "campaign_id": CAMPAIGN_ID,
        "created_at_utc": created_at_utc,
        "classification": {
            "hardware_tested": False,
            "execution_authorized": False,
            "device_io_performed": False,
            "claim_created": False,
            "offline_bundle_only": True,
        },
        "firmware": {
            "environment": FIRMWARE_ENVIRONMENT,
            "file": "firmware.bin",
            "bytes": len(firmware),
            "sha256": sha256(firmware),
            "build_tag": FIRMWARE_BUILD_TAG,
            "driver_api_version": DRIVER_API_VERSION,
            "default_refresh_spi_hz": 1_000_000,
            "ordinary_frame_route_registered": False,
            "arbitrary_frequency_route_registered": False,
        },
        "fixture": {
            "id": FIXTURE,
            "frame_bytes": FRAME_BYTES,
            "full_fnv1a": EXPECTED_FULL_FNV1A,
            "cs1_dtm_fnv1a": EXPECTED_CS1_FNV1A,
            "cs2_dtm_fnv1a": EXPECTED_CS2_FNV1A,
        },
        "controller_mappings": [dict(mapping) for mapping in DEFAULT_MAPPINGS],
        "execution_contract": {
            "firmware_flash_count": 1,
            "j2_p1_must_be_off_during_flash_or_esp32_reboot": True,
            "same_esp32_boot_across_frequency_actions": True,
            "frequency_order_hz": list(FREQUENCIES),
            "first_failure_stops_campaign": True,
            "each_action_requires_independent_workspace_global_claim": True,
            "each_action_requires_explicit_user_authorization": True,
            "automatic_retry": False,
            "automatic_recovery": False,
            "unattended_refresh": False,
        },
        "actions": [
            _action_template(index, frequency)
            for index, frequency in enumerate(FREQUENCIES)
        ],
        "analyzer_contract": {
            "tool": "tools/mf1750_refresh_analyzer.py",
            "schema_version": 2,
            "kind": "mf1750-spi-refresh-sweep",
            "required_action": JOB_ACTION,
            "frequency_order_hz": list(FREQUENCIES),
            "minimum_cold_power_off_s": MINIMUM_PANEL_POWER_OFF_S,
            "requires_serial_job_capture": True,
            "requires_scope_sclk_evidence": True,
            "requires_manual_visual_electrical_thermal_observation": True,
        },
    }


def _validate_action(action: object, index: int) -> None:
    expected = _action_template(index, FREQUENCIES[index])
    if action != expected:
        raise N7CampaignError(f"action template {index} differs from the frozen contract")


def validate_campaign_document(document: object, firmware: bytes) -> Mapping[str, Any]:
    if not isinstance(document, Mapping):
        raise N7CampaignError("campaign.json must contain an object")
    created_at = document.get("created_at_utc")
    expected = build_campaign(firmware, created_at_utc=created_at)  # type: ignore[arg-type]
    if document != expected:
        raise N7CampaignError("campaign document differs from the frozen N7 contract")
    actions = document.get("actions")
    if not isinstance(actions, list) or len(actions) != len(FREQUENCIES):
        raise N7CampaignError("campaign must contain exactly five ordered actions")
    for index, action in enumerate(actions):
        _validate_action(action, index)
    return document


def _read_regular_file(path: Path, label: str) -> bytes:
    if path.is_symlink():
        raise N7CampaignError(f"{label} must not be a symlink")
    try:
        if not path.is_file():
            raise N7CampaignError(f"{label} must be a regular file")
        return path.read_bytes()
    except OSError as error:
        raise N7CampaignError(f"cannot read {label}: {error}") from error


def _strict_json(payload: bytes, label: str) -> object:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise N7CampaignError(f"{label} contains duplicate key {key!r}")
            output[key] = value
        return output

    def reject_constant(value: str) -> object:
        raise N7CampaignError(f"{label} contains unsupported constant {value}")

    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise N7CampaignError(f"invalid {label}: {error}") from error


def _checksum_payload(campaign_payload: bytes, firmware: bytes) -> bytes:
    return (
        f"{sha256(campaign_payload)}  campaign.json\n"
        f"{sha256(firmware)}  firmware.bin\n"
    ).encode("ascii")


def write_campaign_directory(
    destination: Path, firmware: bytes, *, created_at_utc: str
) -> Mapping[str, Any]:
    if not isinstance(destination, Path):
        raise N7CampaignError("destination must be a pathlib.Path")
    if destination.exists() or destination.is_symlink():
        raise N7CampaignError("destination must not already exist")
    manifest = build_campaign(firmware, created_at_utc=created_at_utc)
    campaign_payload = canonical_json(manifest) + b"\n"
    try:
        destination.mkdir(parents=False, exist_ok=False)
        (destination / "campaign.json").write_bytes(campaign_payload)
        (destination / "firmware.bin").write_bytes(firmware)
        (destination / "SHA256SUMS.txt").write_bytes(
            _checksum_payload(campaign_payload, firmware)
        )
    except OSError as error:
        raise N7CampaignError(f"cannot write campaign directory: {error}") from error
    return validate_campaign_directory(destination)


def validate_campaign_directory(directory: Path) -> Mapping[str, Any]:
    if not isinstance(directory, Path):
        raise N7CampaignError("campaign directory must be a pathlib.Path")
    if directory.is_symlink() or not directory.is_dir():
        raise N7CampaignError("campaign path must be a non-symlink directory")
    try:
        names = {entry.name for entry in directory.iterdir()}
    except OSError as error:
        raise N7CampaignError(f"cannot enumerate campaign directory: {error}") from error
    if names != REQUIRED_FILES:
        raise N7CampaignError(
            f"campaign file set differs; expected={sorted(REQUIRED_FILES)}, got={sorted(names)}"
        )
    campaign_payload = _read_regular_file(directory / "campaign.json", "campaign.json")
    firmware = _read_regular_file(directory / "firmware.bin", "firmware.bin")
    checksums = _read_regular_file(directory / "SHA256SUMS.txt", "SHA256SUMS.txt")
    if checksums != _checksum_payload(campaign_payload, firmware):
        raise N7CampaignError("SHA256SUMS.txt does not match campaign bytes")
    document = _strict_json(campaign_payload, "campaign.json")
    validated = validate_campaign_document(document, firmware)
    if canonical_json(validated) + b"\n" != campaign_payload:
        raise N7CampaignError("campaign.json is not canonical JSON plus one newline")
    return validated


def _timestamp(value: str) -> str:
    if not value.endswith("Z"):
        raise argparse.ArgumentTypeError("timestamp must end in Z")
    return value


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("firmware", type=Path)
    compile_parser.add_argument("destination", type=Path)
    compile_parser.add_argument("--created-at-utc", type=_timestamp, required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("directory", type=Path)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "compile":
            firmware = _read_regular_file(args.firmware, "firmware binary")
            document = write_campaign_directory(
                args.destination, firmware, created_at_utc=args.created_at_utc
            )
        else:
            document = validate_campaign_directory(args.directory)
        print(
            json.dumps(
                {
                    "ok": True,
                    "campaign_id": document["campaign_id"],
                    "firmware_sha256": document["firmware"]["sha256"],
                    "hardware_tested": False,
                    "execution_authorized": False,
                    "claim_created": False,
                    "device_io_performed": False,
                },
                sort_keys=True,
            )
        )
        return 0
    except N7CampaignError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
