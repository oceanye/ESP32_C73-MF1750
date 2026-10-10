#!/usr/bin/env python3
"""Materialize the fixed N7 sweep for one physical panel.

The historical N7 bundle freezes the diagnostic firmware and the five
compile-time endpoints, but it intentionally has no physical-panel or limit
authority identity.  This module converts those immutable inputs into a
standard visible-refresh campaign whose action identities and workspace-global
claim filenames are unique to one real panel, the exact N7 firmware bytes, and
an operator-selected J2-off schedule.

Materialization is offline.  It performs no network, serial, GPIO, firmware,
power, authorization, or claim operation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Optional, Sequence
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.epd_frame import (  # noqa: E402
    ControllerMapping,
    controller_stream,
    fnv1a,
    generate_fixture,
    validate_frame,
)
from host.visible_refresh_campaign import (  # noqa: E402
    CAMPAIGN_KIND,
    CampaignContractError,
    build_fixed_action_declaration,
    build_session_contract,
    canonical_json_bytes,
    seal_campaign_contract,
    validate_campaign_contract,
)
from host.visible_refresh_campaign.production_profile import (  # noqa: E402
    ProductionProfileError,
    read_local_regular_file,
)
from tools import mf1750_n7_spi_sweep_campaign as frozen  # noqa: E402


SCHEMA_VERSION = 1
KIND = "mf1750-n7-physical-spi-sweep-materialization"
HASH_SCOPE = (
    "entire N7 physical materialization excluding integrity; UTF-8 JSON with "
    "sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
SOURCE_COMMIT = "172840c091bd963633860b5dfde6f327d30ab665"
CAMPAIGN_ID_PREFIX = "n7-physical-spi-sweep-"
PHYSICAL_CAMPAIGN_FILENAME = "PHYSICAL-CAMPAIGN.json"
MANIFEST_FILENAME = "N7-PHYSICAL-MANIFEST.json"
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_REVIEW_BYTES = 4 * 1024 * 1024
MINIMUM_DRIVER_OFF_SECONDS = float(frozen.MINIMUM_PANEL_POWER_OFF_S)
SCHEDULE_CLASSIFICATION = (
    "operator_selected_supervised_process_schedule_not_supplier_rating"
)

_PLACEHOLDER_RE = re.compile(
    r"(?:^|[-_. ])(?:UNBOUND|UNKNOWN|PLACEHOLDER|DRAFT|TBD|NONE|NULL|TEST)"
    r"(?:$|[-_. ])",
    re.IGNORECASE,
)
_PANEL_KEYS = frozenset({"model", "serial", "board_id", "pcb_revision"})
_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "source",
        "physical_binding",
        "operator_process_schedule",
        "physical_campaign",
        "fixed_actions",
        "execution_contract",
        "classification",
        "integrity",
    }
)
_MAPPINGS = (
    ControllerMapping(0, False, False, False),
    ControllerMapping(1, False, False, False),
)


class N7PhysicalCampaignError(ValueError):
    """The N7 physical campaign or one of its real inputs failed closed."""


def _sha256(value: bytes | Mapping[str, Any]) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N7PhysicalCampaignError(
            f"value is not canonical JSON data: {error}"
        ) from error


def _seconds(value: Any, *, label: str, minimum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise N7PhysicalCampaignError(f"{label} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < minimum:
        raise N7PhysicalCampaignError(f"{label} must be at least {minimum}")
    return normalized


def _strict_json_file(path: Path, *, label: str) -> tuple[Mapping[str, Any], bytes]:
    try:
        snapshot = read_local_regular_file(
            path, label=label, maximum_bytes=MAX_JSON_BYTES
        )
    except ProductionProfileError as error:
        raise N7PhysicalCampaignError(str(error)) from error

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise N7PhysicalCampaignError(
                    f"{label} contains duplicate key {key!r}"
                )
            result[key] = value
        return result

    try:
        value = json.loads(
            snapshot.payload.decode("utf-8"),
            object_pairs_hook=unique,
            parse_constant=lambda token: (_ for _ in ()).throw(
                N7PhysicalCampaignError(
                    f"{label} contains forbidden number {token}"
                )
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N7PhysicalCampaignError(f"{label} is invalid UTF-8 JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise N7PhysicalCampaignError(f"{label} JSON root must be an object")
    if snapshot.payload != canonical_json_bytes(value):
        raise N7PhysicalCampaignError(f"{label} must use canonical JSON bytes")
    return value, snapshot.payload


def _physical_panel(value: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _PANEL_KEYS:
        raise N7PhysicalCampaignError("physical panel fields differ from contract")
    result: dict[str, str] = {}
    for field in ("model", "serial", "board_id", "pcb_revision"):
        item = value[field]
        if (
            not isinstance(item, str)
            or not item
            or item != item.strip()
            or len(item) > 256
            or any(ord(character) < 0x20 for character in item)
            or _PLACEHOLDER_RE.search(item) is not None
        ):
            raise N7PhysicalCampaignError(
                f"physical panel.{field} is blank, placeholder, or malformed"
            )
        result[field] = item
    expected = {
        "model": "MF1750-C73",
        "board_id": "ESP32-C73",
        "pcb_revision": "rev-a1",
    }
    for field, item in expected.items():
        if result[field] != item:
            raise N7PhysicalCampaignError(
                f"physical panel.{field} differs from the frozen N7 hardware"
            )
    return result


def _source_snapshot(directory: Path) -> tuple[Mapping[str, Any], dict[str, Any]]:
    try:
        document = frozen.validate_campaign_directory(directory)
        campaign_payload = (directory / "campaign.json").read_bytes()
        firmware_payload = (directory / "firmware.bin").read_bytes()
        checksum_payload = (directory / "SHA256SUMS.txt").read_bytes()
    except (frozen.N7CampaignError, OSError) as error:
        raise N7PhysicalCampaignError(
            f"frozen N7 source bundle validation failed: {error}"
        ) from error
    return document, {
        "campaign_file_sha256": _sha256(campaign_payload),
        "campaign_canonical_sha256": _sha256(document),
        "firmware_file_sha256": _sha256(firmware_payload),
        "firmware_bytes": len(firmware_payload),
        "checksum_file_sha256": _sha256(checksum_payload),
        "source_commit": SOURCE_COMMIT,
    }


def _review_snapshot(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        artifact = read_local_regular_file(
            path, label=label, maximum_bytes=MAX_REVIEW_BYTES
        )
    except ProductionProfileError as error:
        raise N7PhysicalCampaignError(str(error)) from error
    if not artifact.payload:
        raise N7PhysicalCampaignError(f"{label} must not be empty")
    return artifact.payload, {
        "bytes": len(artifact.payload),
        "sha256": artifact.sha256,
        "actual_bytes_hashed": True,
    }


def _mapping_record(mapping: ControllerMapping) -> dict[str, Any]:
    return {
        "source_half": mapping.source_half,
        "flip_x": mapping.flip_x,
        "flip_y": mapping.flip_y,
        "nibble_swap": mapping.nibble_swap,
    }


def _frame_record() -> Mapping[str, Any]:
    frame = generate_fixture(frozen.FIXTURE)
    validate_frame(frame)
    controllers = []
    for index, mapping in enumerate(_MAPPINGS, start=1):
        stream = controller_stream(frame, mapping)
        controllers.append(
            {
                "controller": f"CS{index}",
                "mapping": _mapping_record(mapping),
                "dtm_bytes": len(stream),
                "dtm_sha256": _sha256(stream),
                "dtm_fnv1a": f"0x{fnv1a(stream):08X}",
            }
        )
    record = {
        "width": 1024,
        "height": 600,
        "bits_per_pixel": 4,
        "bytes": len(frame),
        "sha256": _sha256(frame),
        "fnv1a": f"0x{fnv1a(frame):08X}",
        "controllers": controllers,
    }
    if (
        record["bytes"] != frozen.FRAME_BYTES
        or record["fnv1a"] != f"0x{frozen.EXPECTED_FULL_FNV1A:08X}"
        or controllers[0]["dtm_fnv1a"]
        != f"0x{frozen.EXPECTED_CS1_FNV1A:08X}"
        or controllers[1]["dtm_fnv1a"]
        != f"0x{frozen.EXPECTED_CS2_FNV1A:08X}"
    ):
        raise N7PhysicalCampaignError("MAP_ORIENT_V1 frame identity changed")
    return record


def _build_campaign(
    *,
    panel: Mapping[str, str],
    source: Mapping[str, Any],
    source_record: Mapping[str, Any],
    binding: Mapping[str, Any],
    minimum_interval_seconds: float,
    planned_cooldown_seconds: float,
) -> Mapping[str, Any]:
    identity_seed = {
        "source_campaign_file_sha256": source_record["campaign_file_sha256"],
        "firmware_file_sha256": source_record["firmware_file_sha256"],
        "physical_binding": binding,
        "minimum_interval_seconds": minimum_interval_seconds,
        "planned_cooldown_seconds": planned_cooldown_seconds,
    }
    campaign_id = f"{CAMPAIGN_ID_PREFIX}{_sha256(identity_seed)}"
    frame = _frame_record()
    actions: list[Mapping[str, Any]] = []
    sessions: list[Mapping[str, Any]] = []
    prior_sha: Optional[str] = None
    for index, frequency in enumerate(frozen.FREQUENCIES):
        label = f"{frequency // 1_000_000}mhz"
        action = build_fixed_action_declaration(
            campaign_id=campaign_id,
            session_id=f"n7-{label}-driver-cold",
            cell_id=f"n7-{label}",
            action_id=f"n7-map-orient-v1-{label}",
            phase="spi-sweep",
            frame=frame,
            endpoint=frozen.ROUTES[frequency],
            request_body="none",
            prior_action_identity_sha256=prior_sha,
            prior_scope="campaign" if prior_sha is not None else None,
            minimum_interval_since_prior_seconds=(
                minimum_interval_seconds if prior_sha is not None else 0
            ),
        )
        actions.append(action)
        sessions.append(
            build_session_contract(
                session_id=f"n7-{label}-driver-cold",
                cell_id=f"n7-{label}",
                power_mode="panel_cold_driver_only",
                planned_cooldown_seconds=planned_cooldown_seconds,
                final_power_off_required=True,
                action_identity_sha256s=[action["action_identity_sha256"]],
                minimum_panel_power_off_seconds=planned_cooldown_seconds,
            )
        )
        prior_sha = str(action["action_identity_sha256"])
    firmware = {
        "source_commit": SOURCE_COMMIT,
        "build_tag": frozen.FIRMWARE_BUILD_TAG,
        "binary_sha256": source_record["firmware_file_sha256"],
        "driver_api": frozen.DRIVER_API_VERSION,
    }
    try:
        return seal_campaign_contract(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": CAMPAIGN_KIND,
                "campaign_id": campaign_id,
                "panel": dict(panel),
                "firmware": firmware,
                "actions": actions,
                "sessions": sessions,
                "classification": {
                    "offline_compiled": True,
                    "hardware_execution_authorized": False,
                    "automatic_execution": False,
                    "automatic_retry": False,
                    "automatic_recovery": False,
                    "network_io_performed": False,
                    "device_io_performed": False,
                },
            }
        )
    except CampaignContractError as error:
        raise N7PhysicalCampaignError(
            f"could not build N7 physical campaign: {error}"
        ) from error


def _fixed_actions(campaign: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for frequency, action in zip(frozen.FREQUENCIES, campaign["actions"]):
        key = f"{frequency // 1_000_000}mhz"
        if action["identity"]["request"]["endpoint"] != frozen.ROUTES[frequency]:
            raise N7PhysicalCampaignError("physical action endpoint order changed")
        result[key] = str(action["action_identity_sha256"])
    if len(result) != 5 or len(set(result.values())) != 5:
        raise N7PhysicalCampaignError("N7 physical action identities are incomplete")
    return result


def compile_physical_manifest(
    source_campaign_directory: Path,
    panel_file: Path,
    panel_binding_review_file: Path,
    *,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> dict[str, Any]:
    """Compile and deep-replay one five-action physical N7 campaign."""

    source, source_record = _source_snapshot(source_campaign_directory)
    panel_value, panel_payload = _strict_json_file(
        panel_file, label="physical panel identity"
    )
    panel = _physical_panel(panel_value)
    _review_bytes, review = _review_snapshot(
        panel_binding_review_file, label="N7 panel binding review artifact"
    )
    interval = _seconds(
        minimum_interval_seconds,
        label="minimum_interval_seconds",
        minimum=0.000_000_001,
    )
    cooldown = _seconds(
        planned_cooldown_seconds,
        label="planned_cooldown_seconds",
        minimum=MINIMUM_DRIVER_OFF_SECONDS,
    )
    binding = {
        "panel": panel,
        "panel_file_sha256": _sha256(panel_payload),
        "panel_binding_review_artifact": review,
        "firmware_transition": {
            "from": "physical panel identity only; prior firmware is not inherited",
            "to_build_tag": frozen.FIRMWARE_BUILD_TAG,
            "to_binary_sha256": source_record["firmware_file_sha256"],
            "j2_must_be_off_during_flash_and_controller_boot": True,
        },
    }
    schedule = {
        "classification": SCHEDULE_CLASSIFICATION,
        "not_a_supplier_rating": True,
        "minimum_interval_seconds": interval,
        "planned_cooldown_seconds": cooldown,
        "j2_off_for_entire_cooldown": True,
        "esp32_same_boot_across_all_five_actions": True,
    }
    physical = _build_campaign(
        panel=panel,
        source=source,
        source_record=source_record,
        binding=binding,
        minimum_interval_seconds=interval,
        planned_cooldown_seconds=cooldown,
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            **source_record,
            "campaign_id": source["campaign_id"],
            "frequency_order_hz": list(frozen.FREQUENCIES),
            "routes": [frozen.ROUTES[item] for item in frozen.FREQUENCIES],
        },
        "physical_binding": binding,
        "operator_process_schedule": schedule,
        "physical_campaign": physical,
        "fixed_actions": _fixed_actions(physical),
        "execution_contract": {
            "first_action_requires_fresh_n7_job0": True,
            "same_esp32_boot_across_frequency_actions": True,
            "each_action_requires_driver_only_j2_cold_cycle": True,
            "minimum_driver_off_seconds": cooldown,
            "deep_production_profile_required_before_claim": True,
            "workspace_global_claim_before_network": True,
            "maximum_post_requests_per_action": 1,
            "automatic_retry": False,
            "automatic_recovery": False,
        },
        "classification": {
            "offline_compiled": True,
            "physical_panel_instance_bound": True,
            "firmware_bytes_bound": True,
            "operator_schedule_bound": True,
            "operator_schedule_is_supplier_rating": False,
            "hardware_execution_authorized": False,
            "claim_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
            "qualification_state": "NOT_QUALIFIED",
        },
    }
    result = {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(unsigned),
            "canonical_sha256_scope": HASH_SCOPE,
        },
    }
    return dict(
        validate_physical_manifest(
            result,
            source_campaign_directory,
            panel_file,
            panel_binding_review_file,
            minimum_interval_seconds=interval,
            planned_cooldown_seconds=cooldown,
            _recompile=False,
        )
    )


def validate_physical_manifest(
    manifest: Mapping[str, Any],
    source_campaign_directory: Path,
    panel_file: Path,
    panel_binding_review_file: Path,
    *,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    _recompile: bool = True,
) -> Mapping[str, Any]:
    """Validate structure and, by default, rebuild from every actual input."""

    if not isinstance(manifest, Mapping) or set(manifest) != _ROOT_KEYS:
        raise N7PhysicalCampaignError("N7 physical manifest fields changed")
    unsigned = dict(manifest)
    integrity = unsigned.pop("integrity")
    if integrity != {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": HASH_SCOPE,
    }:
        raise N7PhysicalCampaignError("N7 physical manifest integrity is invalid")
    try:
        campaign = validate_campaign_contract(manifest["physical_campaign"])
    except CampaignContractError as error:
        raise N7PhysicalCampaignError(
            f"N7 physical campaign is invalid: {error}"
        ) from error
    _physical_panel(campaign["panel"])
    if _fixed_actions(campaign) != manifest["fixed_actions"]:
        raise N7PhysicalCampaignError("N7 physical fixed-action map changed")
    if [item["power_mode"] for item in campaign["sessions"]] != [
        "panel_cold_driver_only"
    ] * 5:
        raise N7PhysicalCampaignError("N7 sessions lost driver-only J2 cold semantics")
    if any(
        action["identity"]["request"]["body"] != "none"
        for action in campaign["actions"]
    ):
        raise N7PhysicalCampaignError("N7 diagnostic actions must remain bodyless")
    if _recompile:
        expected = compile_physical_manifest(
            source_campaign_directory,
            panel_file,
            panel_binding_review_file,
            minimum_interval_seconds=minimum_interval_seconds,
            planned_cooldown_seconds=planned_cooldown_seconds,
        )
        if manifest != expected:
            raise N7PhysicalCampaignError(
                "N7 physical manifest differs from actual source inputs"
            )
    return manifest


def _write_new(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise N7PhysicalCampaignError(f"could not write {path.name}: {error}") from error


def publish_physical_bundle(
    source_campaign_directory: Path,
    panel_file: Path,
    panel_binding_review_file: Path,
    output_directory: Path,
    *,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> Mapping[str, Any]:
    """Atomically publish the canonical physical campaign and its lineage."""

    if os.path.lexists(output_directory):
        raise N7PhysicalCampaignError("output directory already exists")
    try:
        parent = output_directory.parent.resolve(strict=True)
    except OSError as error:
        raise N7PhysicalCampaignError(f"output parent is unavailable: {error}") from error
    if not parent.is_dir() or output_directory.name in {"", ".", ".."}:
        raise N7PhysicalCampaignError("output must name a new child directory")
    manifest = compile_physical_manifest(
        source_campaign_directory,
        panel_file,
        panel_binding_review_file,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    destination = parent / output_directory.name
    staging = parent / f".{output_directory.name}.tmp-{uuid.uuid4().hex}"
    published = False
    try:
        staging.mkdir()
        _write_new(
            staging / PHYSICAL_CAMPAIGN_FILENAME,
            canonical_json_bytes(manifest["physical_campaign"]),
        )
        _write_new(staging / MANIFEST_FILENAME, canonical_json_bytes(manifest))
        if os.path.lexists(destination):
            raise N7PhysicalCampaignError("output directory appeared during publish")
        os.rename(staging, destination)
        published = True
    except OSError as error:
        raise N7PhysicalCampaignError(f"could not publish N7 bundle: {error}") from error
    finally:
        if not published:
            for name in (PHYSICAL_CAMPAIGN_FILENAME, MANIFEST_FILENAME):
                try:
                    (staging / name).unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                staging.rmdir()
            except OSError:
                pass
    return manifest


def read_physical_bundle(
    directory: Path,
    source_campaign_directory: Path,
    panel_file: Path,
    panel_binding_review_file: Path,
    *,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> Mapping[str, Any]:
    """Read the exact two-file bundle and replay its complete materialization."""

    try:
        entries = tuple(directory.iterdir())
    except OSError as error:
        raise N7PhysicalCampaignError(f"cannot enumerate N7 bundle: {error}") from error
    if {entry.name for entry in entries} != {
        PHYSICAL_CAMPAIGN_FILENAME,
        MANIFEST_FILENAME,
    } or any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise N7PhysicalCampaignError("N7 bundle must contain exactly two regular files")
    manifest, _ = _strict_json_file(
        directory / MANIFEST_FILENAME, label="N7 physical manifest"
    )
    campaign, _ = _strict_json_file(
        directory / PHYSICAL_CAMPAIGN_FILENAME, label="N7 physical campaign"
    )
    validated = validate_physical_manifest(
        manifest,
        source_campaign_directory,
        panel_file,
        panel_binding_review_file,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    if campaign != validated["physical_campaign"]:
        raise N7PhysicalCampaignError("standalone physical campaign differs from manifest")
    return validated


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-campaign-dir", type=Path, required=True)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--binding-review", type=Path, required=True)
    parser.add_argument("--minimum-interval-seconds", type=float, required=True)
    parser.add_argument("--planned-cooldown-seconds", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    value = publish_physical_bundle(
        args.source_campaign_dir,
        args.panel,
        args.binding_review,
        args.output,
        minimum_interval_seconds=args.minimum_interval_seconds,
        planned_cooldown_seconds=args.planned_cooldown_seconds,
    )
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "KIND",
    "MANIFEST_FILENAME",
    "MINIMUM_DRIVER_OFF_SECONDS",
    "N7PhysicalCampaignError",
    "PHYSICAL_CAMPAIGN_FILENAME",
    "compile_physical_manifest",
    "publish_physical_bundle",
    "read_physical_bundle",
    "validate_physical_manifest",
]
