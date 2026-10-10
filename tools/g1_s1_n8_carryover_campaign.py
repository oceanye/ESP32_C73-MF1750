#!/usr/bin/env python3
"""Compile and describe the offline-only N8 carryover campaign.

N8 owns the direct target-to-target experiments that N3 deliberately avoids.
It reuses only the frozen natural-photo N2P frames and creates new P0 action
identities and workspace-global claim declarations.  This module has no
executor, HTTP client, serial/GPIO path, firmware uploader, claim writer,
authorization generator, retry path, or recovery path.

The default campaign contains five supervised sessions and fifteen visible
actions:

* controller-fresh MAP -> Q1(A1) -> Q4(B) -> Q1(A2);
* warm continuous MAP -> Q1 -> Q2 -> Q3 -> Q4; and
* three controller-fresh temperature-bin MAP -> Q4 sessions.

Only a separately reviewed profile may justify a panel-cold variant.  Normal
N8 sessions explicitly allow J2 to remain on.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
import hashlib
import json
import math
import re
from typing import Any, Mapping, Optional

from host.visible_refresh_campaign import (
    CAMPAIGN_KIND,
    LIMIT_PROFILE_KIND,
    CampaignContractError,
    ResultState,
    build_fixed_action_declaration,
    build_session_contract,
    canonical_json_bytes,
    describe_action_offline,
    evaluate_limit_profile,
    result_file_sha256,
    seal_campaign_contract,
    seal_limit_profile,
    validate_campaign_contract,
    validate_limit_profile,
    validate_result_record,
)
from tools.g1_s1_rc2g_n2_photo_campaign import (
    EXPECTED_MANIFEST_CANONICAL_SHA256 as N2_CANONICAL_SHA256,
    EXPECTED_MANIFEST_FILE_SHA256 as N2_FILE_SHA256,
    FIRMWARE_CONTRACT,
    PANEL_CONTRACT,
    compile_campaign_manifest as compile_n2_manifest,
    validate_compiled_manifest as validate_n2_manifest,
)


SCHEMA_VERSION = 1
MANIFEST_KIND = "mf1750-g1-s1-n8-carryover-offline-manifest"
DESCRIPTION_KIND = "mf1750-g1-s1-n8-action-description"
PLAN_KIND = "mf1750-g1-s1-n8-supervised-plan"
MEASUREMENT_KIND = "mf1750-g1-s1-n8-measurement-registry"
BINDING_KIND = "mf1750-g1-s1-n8-supplier-binding-registry"
TEMPERATURE_PLAN_KIND = "mf1750-g1-s1-n8-temperature-bin-plan"
PANEL_COLD_DESCRIPTION_KIND = "mf1750-g1-s1-n8-panel-cold-variant-description"
CAMPAIGN_ID = "g1-s1-n8-carryover-warm-temperature-v1"

MANIFEST_HASH_SCOPE = (
    "entire N8 manifest excluding integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
DESCRIPTION_HASH_SCOPE = MANIFEST_HASH_SCOPE.replace("N8 manifest", "N8 description")
PLAN_HASH_SCOPE = MANIFEST_HASH_SCOPE.replace("N8 manifest", "N8 supervised plan")

# Compile-time checks make any later default-manifest drift explicit.
EXPECTED_FROZEN_MANIFEST_CANONICAL_SHA256: Optional[str] = (
    "0914e9a63cc18593b27b1f51cf86e7a29a4c65a17b0427b5d4717ee745b8ba91"
)
EXPECTED_FROZEN_MANIFEST_FILE_SHA256: Optional[str] = (
    "5d42dd01036512b836e286bb7c2f0735df36523b1434b84eb12bbba471c1e4ab"
)

N8_CELLS = ("MAP", "Q1", "Q2", "Q3", "Q4")
N8_SEQUENCE_IDS = (
    "n8-aba-q1-q4-q1",
    "n8-warm-q1-q2-q3-q4",
    "n8-temperature-low-q4",
    "n8-temperature-nominal-q4",
    "n8-temperature-high-q4",
)
TEMPERATURE_BIN_IDS = ("supplier-low", "supplier-nominal", "supplier-high")

_SEQUENCE_SPECS = (
    {
        "sequence_id": N8_SEQUENCE_IDS[0],
        "purpose": "direct-target-carryover-a-to-b-to-a",
        "power_mode": "controller_fresh_boot",
        "temperature_bin_id": None,
        "steps": (("MAP", "MAP"), ("A1", "Q1"), ("B", "Q4"), ("A2", "Q1")),
    },
    {
        "sequence_id": N8_SEQUENCE_IDS[1],
        "purpose": "warm-sequential-four-algorithm-observation",
        "power_mode": "supervised_continuous",
        "temperature_bin_id": None,
        "steps": (
            ("MAP", "MAP"),
            ("W1", "Q1"),
            ("W2", "Q2"),
            ("W3", "Q3"),
            ("W4", "Q4"),
        ),
    },
    {
        "sequence_id": N8_SEQUENCE_IDS[2],
        "purpose": "externally-measured-temperature-bin-observation",
        "power_mode": "controller_fresh_boot",
        "temperature_bin_id": TEMPERATURE_BIN_IDS[0],
        "steps": (("MAP", "MAP"), ("TARGET", "Q4")),
    },
    {
        "sequence_id": N8_SEQUENCE_IDS[3],
        "purpose": "externally-measured-temperature-bin-observation",
        "power_mode": "controller_fresh_boot",
        "temperature_bin_id": TEMPERATURE_BIN_IDS[1],
        "steps": (("MAP", "MAP"), ("TARGET", "Q4")),
    },
    {
        "sequence_id": N8_SEQUENCE_IDS[4],
        "purpose": "externally-measured-temperature-bin-observation",
        "power_mode": "controller_fresh_boot",
        "temperature_bin_id": TEMPERATURE_BIN_IDS[2],
        "steps": (("MAP", "MAP"), ("TARGET", "Q4")),
    },
)

_P0_CLASSIFICATION = {
    "offline_compiled": True,
    "hardware_execution_authorized": False,
    "automatic_execution": False,
    "automatic_retry": False,
    "automatic_recovery": False,
    "network_io_performed": False,
    "device_io_performed": False,
}
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class N8CampaignError(ValueError):
    """An N8 manifest or offline plan failed closed."""


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N8CampaignError(f"value is not canonical JSON data: {error}") from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _integrity(unsigned: Mapping[str, Any], scope: str) -> dict[str, str]:
    return {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": scope,
    }


def _require_sha256(
    value: Any, *, label: str, nullable: bool = False
) -> Optional[str]:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        suffix = " or null" if nullable else ""
        raise N8CampaignError(f"{label} must be 64 lowercase hexadecimal digits{suffix}")
    return value


def _number(
    value: Any,
    *,
    label: str,
    nullable: bool = False,
    minimum: Optional[float] = None,
) -> Optional[float]:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        suffix = " or null" if nullable else ""
        raise N8CampaignError(f"{label} must be a finite number{suffix}")
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise N8CampaignError(f"{label} is outside the allowed finite range")
    return result


def _exact(value: Any, *, label: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise N8CampaignError(f"{label} must be an object")
    if set(value) != keys:
        missing = sorted(keys - set(value))
        extra = sorted(set(value) - keys)
        raise N8CampaignError(f"{label} keys changed; missing={missing}, extra={extra}")
    return value


@lru_cache(maxsize=1)
def _n2_manifest_bytes() -> bytes:
    manifest = compile_n2_manifest()
    validate_n2_manifest(manifest)
    payload = canonical_json_bytes(manifest)
    if N2_CANONICAL_SHA256 is None or N2_FILE_SHA256 is None:
        raise N8CampaignError("the N2P natural-photo source is not frozen")
    if (
        manifest["manifest_integrity"]["canonical_sha256"] != N2_CANONICAL_SHA256
        or _sha256(payload) != N2_FILE_SHA256
    ):
        raise N8CampaignError("the frozen N2P source identity changed")
    return payload


def _n2_manifest() -> Mapping[str, Any]:
    return json.loads(_n2_manifest_bytes().decode("utf-8"))


def _p0_frame(candidate_frame: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "width": candidate_frame["width"],
        "height": candidate_frame["height"],
        "bits_per_pixel": candidate_frame["bits_per_pixel"],
        "bytes": candidate_frame["bytes"],
        "sha256": candidate_frame["sha256"],
        "fnv1a": candidate_frame["fnv1a"],
        "controllers": _snapshot(candidate_frame["controllers"]),
    }


def _source_and_frames(n2: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    cells = {cell["cell_id"]: cell for cell in n2["cells"]}
    if tuple(cells) != ("Q1", "Q2", "Q3", "Q4"):
        raise N8CampaignError("N2P candidate order changed")
    if (
        n2["classification"]["natural_photo_input"] is not True
        or n2["readiness"]["candidate_set_ready"] is not True
        or n2["scientific_gate"]["scientific_gate_pass"] is not True
    ):
        raise N8CampaignError("N2P natural-photo candidate gate is no longer PASS")

    source = n2["shared_evidence"]["source"]
    mapped = n2["shared_evidence"]["mapped"]
    profile = n2["shared_evidence"]["profile"]
    source_record = {
        "kind": n2["kind"],
        "campaign_id": n2["campaign_id"],
        "canonical_sha256": N2_CANONICAL_SHA256,
        "file_sha256": N2_FILE_SHA256,
        "natural_photo_input": True,
        "source_input_sha256": source["input"]["sha256"],
        "normalized_pixels_sha256": source["pixels_sha256"],
        "mapped_rgb8_sha256": mapped["rgb8_sha256"],
        "mapping_report_sha256": mapped["mapping_report_sha256"],
        "profile_canonical_sha256": profile["canonical_sha256"],
        "profile_characterization_level": profile["characterization_level"],
        "profile_is_measured_panel_characterization": False,
        "scientific_gate_canonical_sha256": _sha256(n2["scientific_gate"]),
    }
    frames: dict[str, Any] = {
        "MAP": {
            "source_id": "MAP",
            "algorithm": "map-orient-v1",
            "frame": _snapshot(n2["shared_evidence"]["map_primer"]["frame"]),
        }
    }
    for cell_id, cell in cells.items():
        frames[cell_id] = {
            "source_id": cell_id,
            "algorithm": cell["algorithm"],
            "frame": _p0_frame(cell["candidate"]["frame"]),
            "candidate_manifest_canonical_sha256": cell["candidate"]["artifact"][
                "manifest_canonical_sha256"
            ],
        }
    return source_record, frames


def build_measurement_registry(
    *,
    external_temperature_sensor_sha256: Optional[str] = None,
    external_temperature_calibration_sha256: Optional[str] = None,
    external_temperature_location_sha256: Optional[str] = None,
    external_temperature_u95_c: Optional[int | float] = None,
    camera_body_sha256: Optional[str] = None,
    camera_lens_sha256: Optional[str] = None,
    camera_mount_sha256: Optional[str] = None,
    fixed_exposure_profile_sha256: Optional[str] = None,
    camera_crop_sha256: Optional[str] = None,
    illumination_sha256: Optional[str] = None,
    electrical_meter_sha256: Optional[str] = None,
    timing_clock_sha256: Optional[str] = None,
) -> dict[str, Any]:
    """Build evidence identities; null values remain valid but hardware-blocking."""

    registry = {
        "schema_version": SCHEMA_VERSION,
        "kind": MEASUREMENT_KIND,
        "external_temperature": {
            "required": True,
            "units": "degC",
            "sensor_asset_sha256": external_temperature_sensor_sha256,
            "calibration_artifact_sha256": external_temperature_calibration_sha256,
            "measurement_location_sha256": external_temperature_location_sha256,
            "uncertainty_u95_c": external_temperature_u95_c,
            "internal_temperature_available": False,
            "swc_temperature_available": False,
            "inference_from_internal_or_swc_forbidden": True,
        },
        "camera": {
            "fixed_across_campaign": True,
            "raw_capture_required": True,
            "manual_exposure_required": True,
            "manual_white_balance_required": True,
            "body_asset_sha256": camera_body_sha256,
            "lens_asset_sha256": camera_lens_sha256,
            "mount_asset_sha256": camera_mount_sha256,
            "fixed_exposure_profile_sha256": fixed_exposure_profile_sha256,
            "crop_asset_sha256": camera_crop_sha256,
            "illumination_asset_sha256": illumination_sha256,
        },
        "electrical": {
            "meter_asset_sha256": electrical_meter_sha256,
            "required_fields": [
                "pre_voltage_v",
                "pre_idle_current_a",
                "post_voltage_v",
                "post_idle_current_a",
                "peak_current_a",
                "constant_voltage_mode",
            ],
        },
        "timing": {
            "clock_asset_sha256": timing_clock_sha256,
            "required_fields": [
                "queue_delay_ms",
                "job_duration_ms",
                "driver_total_ms",
                "cs1_upload_ms",
                "cs2_upload_ms",
                "pon_ms",
                "drf_ms",
                "pof_ms",
                "post_psr_ms",
            ],
        },
    }
    validate_measurement_registry(registry)
    return registry


def validate_measurement_registry(registry: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _exact(
        registry,
        label="N8 measurement registry",
        keys={"schema_version", "kind", "external_temperature", "camera", "electrical", "timing"},
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != MEASUREMENT_KIND:
        raise N8CampaignError("N8 measurement registry schema or kind is invalid")
    temperature = _exact(
        root["external_temperature"],
        label="external temperature registry",
        keys={
            "required",
            "units",
            "sensor_asset_sha256",
            "calibration_artifact_sha256",
            "measurement_location_sha256",
            "uncertainty_u95_c",
            "internal_temperature_available",
            "swc_temperature_available",
            "inference_from_internal_or_swc_forbidden",
        },
    )
    if temperature["required"] is not True or temperature["units"] != "degC":
        raise N8CampaignError("external temperature measurement must remain mandatory in degC")
    if (
        temperature["internal_temperature_available"] is not False
        or temperature["swc_temperature_available"] is not False
        or temperature["inference_from_internal_or_swc_forbidden"] is not True
    ):
        raise N8CampaignError("internal temperature/SWC unavailability policy changed")
    for field in (
        "sensor_asset_sha256",
        "calibration_artifact_sha256",
        "measurement_location_sha256",
    ):
        _require_sha256(temperature[field], label=f"external temperature {field}", nullable=True)
    _number(
        temperature["uncertainty_u95_c"],
        label="external temperature uncertainty_u95_c",
        nullable=True,
        minimum=0,
    )
    camera = _exact(
        root["camera"],
        label="camera registry",
        keys={
            "fixed_across_campaign",
            "raw_capture_required",
            "manual_exposure_required",
            "manual_white_balance_required",
            "body_asset_sha256",
            "lens_asset_sha256",
            "mount_asset_sha256",
            "fixed_exposure_profile_sha256",
            "crop_asset_sha256",
            "illumination_asset_sha256",
        },
    )
    for field in (
        "fixed_across_campaign",
        "raw_capture_required",
        "manual_exposure_required",
        "manual_white_balance_required",
    ):
        if camera[field] is not True:
            raise N8CampaignError(f"camera {field} must remain true")
    for field in (
        "body_asset_sha256",
        "lens_asset_sha256",
        "mount_asset_sha256",
        "fixed_exposure_profile_sha256",
        "crop_asset_sha256",
        "illumination_asset_sha256",
    ):
        _require_sha256(camera[field], label=f"camera {field}", nullable=True)
    electrical = _exact(
        root["electrical"],
        label="electrical registry",
        keys={"meter_asset_sha256", "required_fields"},
    )
    _require_sha256(
        electrical["meter_asset_sha256"],
        label="electrical meter asset",
        nullable=True,
    )
    if electrical["required_fields"] != [
        "pre_voltage_v",
        "pre_idle_current_a",
        "post_voltage_v",
        "post_idle_current_a",
        "peak_current_a",
        "constant_voltage_mode",
    ]:
        raise N8CampaignError("electrical measurement fields changed")
    timing = _exact(
        root["timing"],
        label="timing registry",
        keys={"clock_asset_sha256", "required_fields"},
    )
    _require_sha256(timing["clock_asset_sha256"], label="timing clock", nullable=True)
    if timing["required_fields"] != [
        "queue_delay_ms",
        "job_duration_ms",
        "driver_total_ms",
        "cs1_upload_ms",
        "cs2_upload_ms",
        "pon_ms",
        "drf_ms",
        "pof_ms",
        "post_psr_ms",
    ]:
        raise N8CampaignError("timing measurement fields changed")
    return root


def build_binding_registry(
    *,
    supplier_limit_document_sha256: Optional[str] = None,
    panel_instance_binding_sha256: Optional[str] = None,
    firmware_build_binding_sha256: Optional[str] = None,
) -> dict[str, Any]:
    registry = {
        "schema_version": SCHEMA_VERSION,
        "kind": BINDING_KIND,
        "supplier_limit_document_sha256": supplier_limit_document_sha256,
        "panel_instance_binding_sha256": panel_instance_binding_sha256,
        "firmware_build_binding_sha256": firmware_build_binding_sha256,
    }
    validate_binding_registry(registry)
    return registry


def validate_binding_registry(registry: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _exact(
        registry,
        label="N8 binding registry",
        keys={
            "schema_version",
            "kind",
            "supplier_limit_document_sha256",
            "panel_instance_binding_sha256",
            "firmware_build_binding_sha256",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != BINDING_KIND:
        raise N8CampaignError("N8 binding registry schema or kind is invalid")
    for field in (
        "supplier_limit_document_sha256",
        "panel_instance_binding_sha256",
        "firmware_build_binding_sha256",
    ):
        _require_sha256(root[field], label=f"binding registry {field}", nullable=True)
    return root


def build_temperature_bin_plan(
    *,
    supplier_definition_sha256: Optional[str] = None,
    low_minimum_c: Optional[int | float] = None,
    low_maximum_c: Optional[int | float] = None,
    nominal_minimum_c: Optional[int | float] = None,
    nominal_maximum_c: Optional[int | float] = None,
    high_minimum_c: Optional[int | float] = None,
    high_maximum_c: Optional[int | float] = None,
) -> dict[str, Any]:
    plan = {
        "schema_version": SCHEMA_VERSION,
        "kind": TEMPERATURE_PLAN_KIND,
        "supplier_definition_sha256": supplier_definition_sha256,
        "measurement_source": "external-panel-location-only",
        "internal_temperature_inference_allowed": False,
        "bins": [
            {
                "bin_id": "supplier-low",
                "minimum_c": low_minimum_c,
                "maximum_c": low_maximum_c,
            },
            {
                "bin_id": "supplier-nominal",
                "minimum_c": nominal_minimum_c,
                "maximum_c": nominal_maximum_c,
            },
            {
                "bin_id": "supplier-high",
                "minimum_c": high_minimum_c,
                "maximum_c": high_maximum_c,
            },
        ],
    }
    validate_temperature_bin_plan(plan)
    return plan


def validate_temperature_bin_plan(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _exact(
        plan,
        label="N8 temperature-bin plan",
        keys={
            "schema_version",
            "kind",
            "supplier_definition_sha256",
            "measurement_source",
            "internal_temperature_inference_allowed",
            "bins",
        },
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != TEMPERATURE_PLAN_KIND
        or root["measurement_source"] != "external-panel-location-only"
        or root["internal_temperature_inference_allowed"] is not False
    ):
        raise N8CampaignError("N8 temperature-bin policy changed")
    _require_sha256(
        root["supplier_definition_sha256"],
        label="temperature supplier definition",
        nullable=True,
    )
    if not isinstance(root["bins"], list) or len(root["bins"]) != 3:
        raise N8CampaignError("N8 temperature plan requires exactly three bins")
    if [value.get("bin_id") for value in root["bins"]] != list(TEMPERATURE_BIN_IDS):
        raise N8CampaignError("N8 temperature-bin order changed")
    previous_maximum: Optional[float] = None
    for index, value in enumerate(root["bins"]):
        bin_record = _exact(
            value,
            label=f"temperature bin {index}",
            keys={"bin_id", "minimum_c", "maximum_c"},
        )
        minimum = _number(
            bin_record["minimum_c"],
            label=f"temperature bin {index} minimum",
            nullable=True,
        )
        maximum = _number(
            bin_record["maximum_c"],
            label=f"temperature bin {index} maximum",
            nullable=True,
        )
        if (minimum is None) != (maximum is None):
            raise N8CampaignError("temperature-bin endpoints must both be set or both be null")
        if minimum is not None and maximum is not None:
            if minimum >= maximum:
                raise N8CampaignError("temperature bin is empty")
            if previous_maximum is not None and minimum < previous_maximum:
                raise N8CampaignError("temperature bins overlap or are out of order")
            previous_maximum = maximum
    return root


def _build_draft_limit_profile(campaign: Mapping[str, Any]) -> dict[str, Any]:
    return seal_limit_profile(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": LIMIT_PROFILE_KIND,
            "profile_id": "n8-draft-missing-supplier-limits",
            "profile_version": "1.0.0",
            "panel": _snapshot(campaign["panel"]),
            "firmware": _snapshot(campaign["firmware"]),
            "action_allowlist": [],
            "limits": {
                "maximum_campaign_visible_refreshes": None,
                "maximum_session_visible_refreshes": None,
                "maximum_consecutive_visible_refreshes": None,
                "minimum_interval_seconds": None,
                "minimum_cooldown_seconds": None,
                "minimum_start_temperature_c": None,
                "maximum_start_temperature_c": None,
                "maximum_post_refresh_temperature_c": None,
            },
            "usage": {
                "cumulative_visible_refresh_count": None,
                "session_visible_refresh_count": None,
                "consecutive_visible_refresh_count": None,
                "last_visible_refresh_completed_at": None,
                "snapshot_at": None,
                "evidence_sha256": None,
            },
            "validity": {"valid_from": None, "expires_at": None},
            "review": {
                "approved": False,
                "reviewer_id": None,
                "reviewed_at": None,
                "review_artifact_sha256": None,
            },
        }
    )


def _build_p0_campaign(
    *,
    panel: Mapping[str, Any],
    firmware: Mapping[str, Any],
    frames: Mapping[str, Any],
    minimum_interval_seconds: float,
    planned_cooldown_seconds: float,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = []
    sessions: list[dict[str, Any]] = []
    sequences: list[dict[str, Any]] = []
    for spec in _SEQUENCE_SPECS:
        sequence_id = str(spec["sequence_id"])
        cell_id = sequence_id
        prior_sha: Optional[str] = None
        action_records: list[dict[str, Any]] = []
        session_actions: list[str] = []
        for ordinal, (role, source_id) in enumerate(spec["steps"], start=1):
            action = build_fixed_action_declaration(
                campaign_id=CAMPAIGN_ID,
                session_id=sequence_id,
                cell_id=cell_id,
                action_id=f"{sequence_id}-{role.lower()}",
                phase=role.lower(),
                frame=frames[source_id]["frame"],
                prior_action_identity_sha256=prior_sha,
                prior_scope="same_cell" if prior_sha is not None else None,
                minimum_interval_since_prior_seconds=(
                    minimum_interval_seconds if prior_sha is not None else 0
                ),
            )
            action_sha = action["action_identity_sha256"]
            action_records.append(
                {
                    "ordinal": ordinal,
                    "role": role,
                    "frame_source_id": source_id,
                    "frame_sha256": frames[source_id]["frame"]["sha256"],
                    "action_identity_sha256": action_sha,
                    "claim_declaration": _snapshot(action["claim"]),
                    "prior_result_requirement": (
                        {
                            "required": False,
                            "reason": "session-root-action-has-no-predecessor",
                            "prior_action_identity_sha256": None,
                            "required_result_state": None,
                            "required_result_file_sha256": None,
                        }
                        if prior_sha is None
                        else {
                            "required": True,
                            "reason": "bind-exact-whole-file-result-before-description",
                            "prior_action_identity_sha256": prior_sha,
                            "required_result_state": ResultState.PASS.value,
                            "required_result_file_sha256": None,
                        }
                    ),
                }
            )
            actions.append(action)
            session_actions.append(action_sha)
            prior_sha = action_sha
        session = build_session_contract(
            session_id=sequence_id,
            cell_id=cell_id,
            power_mode=str(spec["power_mode"]),
            planned_cooldown_seconds=planned_cooldown_seconds,
            final_power_off_required=False,
            action_identity_sha256s=session_actions,
        )
        sessions.append(session)
        sequences.append(
            {
                "sequence_id": sequence_id,
                "purpose": spec["purpose"],
                "temperature_bin_id": spec["temperature_bin_id"],
                "session_canonical_sha256": session["integrity"]["canonical_sha256"],
                "power_mode": spec["power_mode"],
                "requires_controller_fresh_boot": session[
                    "requires_controller_fresh_boot"
                ],
                "requires_panel_power_cycle": False,
                "j2_may_remain_on_before_session": True,
                "automatic_advance": False,
                "actions": action_records,
            }
        )
    campaign = seal_campaign_contract(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": CAMPAIGN_KIND,
            "campaign_id": CAMPAIGN_ID,
            "panel": _snapshot(panel),
            "firmware": _snapshot(firmware),
            "actions": actions,
            "sessions": sessions,
            "classification": dict(_P0_CLASSIFICATION),
        }
    )
    return campaign, sequences, actions


def _measurement_blockers(registry: Mapping[str, Any]) -> list[str]:
    root = validate_measurement_registry(registry)
    blockers: list[str] = []
    temperature = root["external_temperature"]
    for field in (
        "sensor_asset_sha256",
        "calibration_artifact_sha256",
        "measurement_location_sha256",
        "uncertainty_u95_c",
    ):
        if temperature[field] is None:
            blockers.append(f"missing_external_temperature:{field}")
    for field in (
        "body_asset_sha256",
        "lens_asset_sha256",
        "mount_asset_sha256",
        "fixed_exposure_profile_sha256",
        "crop_asset_sha256",
        "illumination_asset_sha256",
    ):
        if root["camera"][field] is None:
            blockers.append(f"missing_camera_asset:{field}")
    if root["electrical"]["meter_asset_sha256"] is None:
        blockers.append("missing_electrical_meter_asset")
    if root["timing"]["clock_asset_sha256"] is None:
        blockers.append("missing_timing_clock_asset")
    return blockers


def _binding_blockers(
    *,
    panel: Mapping[str, Any],
    firmware: Mapping[str, Any],
    profile: Mapping[str, Any],
    bindings: Mapping[str, Any],
) -> list[str]:
    root = validate_binding_registry(bindings)
    validated_profile = validate_limit_profile(profile)
    blockers: list[str] = []
    if str(panel.get("serial", "")).startswith("UNBOUND-"):
        blockers.append("panel_instance_unbound")
    if validated_profile["panel"] != panel:
        blockers.append("limit_profile_panel_mismatch")
    if validated_profile["firmware"] != firmware:
        blockers.append("limit_profile_firmware_mismatch")
    for field in (
        "supplier_limit_document_sha256",
        "panel_instance_binding_sha256",
        "firmware_build_binding_sha256",
    ):
        if root[field] is None:
            blockers.append(f"missing_binding:{field}")
    limits = validated_profile["limits"]
    for field in (
        "maximum_campaign_visible_refreshes",
        "maximum_session_visible_refreshes",
        "maximum_consecutive_visible_refreshes",
        "minimum_interval_seconds",
        "minimum_cooldown_seconds",
        "minimum_start_temperature_c",
        "maximum_start_temperature_c",
        "maximum_post_refresh_temperature_c",
    ):
        if limits[field] is None:
            blockers.append(f"missing_supplier_limit:{field}")
    if validated_profile["review"]["approved"] is not True:
        blockers.append("supplier_limit_profile_not_reviewed")
    return blockers


def _temperature_bin_blockers(plan: Mapping[str, Any]) -> list[str]:
    root = validate_temperature_bin_plan(plan)
    blockers: list[str] = []
    if root["supplier_definition_sha256"] is None:
        blockers.append("missing_temperature_bin_supplier_definition")
    for value in root["bins"]:
        if value["minimum_c"] is None or value["maximum_c"] is None:
            blockers.append(f"missing_temperature_bin_bounds:{value['bin_id']}")
    return blockers


def _power_semantics() -> dict[str, Any]:
    return {
        "supervised_continuous": {
            "controller_fresh_boot_required": False,
            "panel_power_cycle_required": False,
            "j2_may_remain_on": True,
            "used_by_default": [N8_SEQUENCE_IDS[1]],
        },
        "controller_fresh_boot": {
            "controller_fresh_boot_required": True,
            "panel_power_cycle_required": False,
            "j2_may_remain_on": True,
            "used_by_default": [
                N8_SEQUENCE_IDS[0],
                N8_SEQUENCE_IDS[2],
                N8_SEQUENCE_IDS[3],
                N8_SEQUENCE_IDS[4],
            ],
        },
        "panel_cold_cycle": {
            "controller_fresh_boot_required": True,
            "panel_power_cycle_required": True,
            "j2_may_remain_on": False,
            "used_by_default": [],
            "requires_distinct_recompiled_p0_session": True,
            "requires_current_reviewed_limit_profile": True,
            "requires_positive_measured_panel_off_interval": True,
        },
    }


def _analysis_contract() -> dict[str, Any]:
    return {
        "qualification_state": "NOT_QUALIFIED",
        "descriptive_only": True,
        "temperature_observations_per_bin": 1,
        "population_inference_allowed": False,
        "causal_threshold_conclusion_allowed": False,
        "single_aba_sequence_qualifies_carryover": False,
        "single_observation_per_bin_qualifies_temperature_behavior": False,
        "complete_pass_chain_label": "EVIDENCE_CHAIN_COMPLETE_DESCRIPTIVE_ONLY",
    }


def compile_n8_manifest(
    *,
    panel: Optional[Mapping[str, Any]] = None,
    firmware: Optional[Mapping[str, Any]] = None,
    measurement_registry: Optional[Mapping[str, Any]] = None,
    binding_registry: Optional[Mapping[str, Any]] = None,
    temperature_bin_plan: Optional[Mapping[str, Any]] = None,
    limit_profile: Optional[Mapping[str, Any]] = None,
    minimum_interval_seconds: int | float = 0,
    planned_cooldown_seconds: int | float = 0,
) -> dict[str, Any]:
    """Compile all N8 schedules without claims, authorization, or device I/O."""

    frozen_default = all(
        value is None
        for value in (
            panel,
            firmware,
            measurement_registry,
            binding_registry,
            temperature_bin_plan,
            limit_profile,
        )
    ) and minimum_interval_seconds == 0 and planned_cooldown_seconds == 0
    selected_panel = _snapshot(PANEL_CONTRACT if panel is None else panel)
    selected_firmware = _snapshot(FIRMWARE_CONTRACT if firmware is None else firmware)
    selected_measurements = _snapshot(
        build_measurement_registry()
        if measurement_registry is None
        else measurement_registry
    )
    selected_bindings = _snapshot(
        build_binding_registry() if binding_registry is None else binding_registry
    )
    selected_bins = _snapshot(
        build_temperature_bin_plan()
        if temperature_bin_plan is None
        else temperature_bin_plan
    )
    validate_measurement_registry(selected_measurements)
    validate_binding_registry(selected_bindings)
    validate_temperature_bin_plan(selected_bins)
    interval = _number(
        minimum_interval_seconds,
        label="minimum_interval_seconds",
        minimum=0,
    )
    cooldown = _number(
        planned_cooldown_seconds,
        label="planned_cooldown_seconds",
        minimum=0,
    )
    assert interval is not None and cooldown is not None

    n2 = _n2_manifest()
    source, frames = _source_and_frames(n2)
    p0_campaign, sequences, actions = _build_p0_campaign(
        panel=selected_panel,
        firmware=selected_firmware,
        frames=frames,
        minimum_interval_seconds=interval,
        planned_cooldown_seconds=cooldown,
    )
    selected_profile = _snapshot(
        _build_draft_limit_profile(p0_campaign)
        if limit_profile is None
        else limit_profile
    )
    validate_limit_profile(selected_profile)
    blockers = [
        *_binding_blockers(
            panel=selected_panel,
            firmware=selected_firmware,
            profile=selected_profile,
            bindings=selected_bindings,
        ),
        *_measurement_blockers(selected_measurements),
        *_temperature_bin_blockers(selected_bins),
        "limit_profile_validity_and_usage_not_evaluated",
        "current_external_temperature_measurement_not_supplied",
        "current_electrical_and_operator_gates_not_evaluated",
        "exact_action_authorization_not_supplied",
    ]
    unique_blockers = list(dict.fromkeys(blockers))
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "campaign_id": CAMPAIGN_ID,
        "purpose": "direct-carryover-warm-sequential-and-temperature-bin-offline-planning",
        "source_n2": source,
        "panel": selected_panel,
        "firmware": selected_firmware,
        "frames": frames,
        "p0_campaign": p0_campaign,
        "sequences": sequences,
        "power_semantics": _power_semantics(),
        "temperature_bin_plan": selected_bins,
        "measurement_registry": selected_measurements,
        "binding_registry": selected_bindings,
        "limit_profile": selected_profile,
        "dependency_contract": {
            "session_root_actions": 5,
            "dependent_actions_requiring_exact_prior_pass_result_file_sha256": 10,
            "required_state": ResultState.PASS.value,
            "binding_time": "describe-or-plan-before-each-dependent-action",
            "root_exception": (
                "a DAG root has no predecessor; every non-root visible action requires "
                "the immediately preceding whole result file SHA-256 and PASS state"
            ),
            "cross_sequence_result_binding_allowed": False,
        },
        "scheduler_contract": {
            "mode": "describe-plan-only",
            "automatic_advance": False,
            "unattended_operation": False,
            "claim_creation": False,
            "authorization_creation": False,
            "execution_runner_present": False,
            "abnormal_terminal_state": ResultState.UNKNOWN_DO_NOT_RETRY.value,
            "remaining_actions_stop_after_abnormality": True,
        },
        "analysis_contract": _analysis_contract(),
        "classification": {
            "offline_compiled": True,
            "software_ready": True,
            "hardware_ready": False,
            "hardware_execution_authorized": False,
            "automatic_execution": False,
            "automatic_retry": False,
            "automatic_recovery": False,
            "claim_created": False,
            "authorization_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
        },
        "hardware_readiness": {
            "ready": False,
            "internal_temperature_available": False,
            "swc_temperature_available": False,
            "inference_from_internal_or_swc_forbidden": True,
            "blockers": unique_blockers,
        },
        "compiler_effects": {
            "visible_action_declarations": len(actions),
            "workspace_global_claim_declarations": len(actions),
            "sessions": len(sequences),
            "dependent_prior_result_bindings": sum(
                len(sequence["actions"]) - 1 for sequence in sequences
            ),
            "claims_created": 0,
            "authorizations_created": 0,
            "network_requests": 0,
            "device_operations": 0,
            "visible_refreshes": 0,
        },
    }
    manifest = {**unsigned, "integrity": _integrity(unsigned, MANIFEST_HASH_SCOPE)}
    validate_n8_manifest(manifest)
    if frozen_default:
        canonical_sha = manifest["integrity"]["canonical_sha256"]
        file_sha = _sha256(manifest)
        if (
            EXPECTED_FROZEN_MANIFEST_CANONICAL_SHA256 is not None
            and canonical_sha != EXPECTED_FROZEN_MANIFEST_CANONICAL_SHA256
        ):
            raise N8CampaignError("frozen N8 manifest canonical identity changed")
        if (
            EXPECTED_FROZEN_MANIFEST_FILE_SHA256 is not None
            and file_sha != EXPECTED_FROZEN_MANIFEST_FILE_SHA256
        ):
            raise N8CampaignError("frozen N8 manifest whole-file identity changed")
    return manifest


def validate_n8_manifest(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _exact(
        manifest,
        label="N8 manifest",
        keys={
            "schema_version",
            "kind",
            "campaign_id",
            "purpose",
            "source_n2",
            "panel",
            "firmware",
            "frames",
            "p0_campaign",
            "sequences",
            "power_semantics",
            "temperature_bin_plan",
            "measurement_registry",
            "binding_registry",
            "limit_profile",
            "dependency_contract",
            "scheduler_contract",
            "analysis_contract",
            "classification",
            "hardware_readiness",
            "compiler_effects",
            "integrity",
        },
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != MANIFEST_KIND
        or root["campaign_id"] != CAMPAIGN_ID
        or root["purpose"]
        != "direct-carryover-warm-sequential-and-temperature-bin-offline-planning"
    ):
        raise N8CampaignError("N8 manifest schema, kind, or campaign ID changed")
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if integrity != _integrity(unsigned, MANIFEST_HASH_SCOPE):
        raise N8CampaignError("N8 manifest canonical integrity is invalid")
    expected_source, expected_frames = _source_and_frames(_n2_manifest())
    if root["source_n2"] != expected_source or root["frames"] != expected_frames:
        raise N8CampaignError("N8 source or frame bundle differs from frozen N2P")

    try:
        campaign = validate_campaign_contract(root["p0_campaign"])
        validate_limit_profile(root["limit_profile"])
    except CampaignContractError as error:
        raise N8CampaignError(f"nested P0 contract is invalid: {error}") from error
    if campaign["campaign_id"] != CAMPAIGN_ID:
        raise N8CampaignError("nested P0 campaign ID changed")
    if campaign["panel"] != root["panel"] or campaign["firmware"] != root["firmware"]:
        raise N8CampaignError("outer panel/firmware differs from the P0 campaign")
    validate_measurement_registry(root["measurement_registry"])
    validate_binding_registry(root["binding_registry"])
    validate_temperature_bin_plan(root["temperature_bin_plan"])
    if set(root["frames"]) != set(N8_CELLS):
        raise N8CampaignError("N8 frozen frame registry changed")

    if not isinstance(root["sequences"], list) or len(root["sequences"]) != 5:
        raise N8CampaignError("N8 must contain exactly five sequences")
    if [value.get("sequence_id") for value in root["sequences"]] != list(N8_SEQUENCE_IDS):
        raise N8CampaignError("N8 sequence order changed")
    p0_actions = {
        action["action_identity_sha256"]: action for action in campaign["actions"]
    }
    p0_sessions = {session["session_id"]: session for session in campaign["sessions"]}
    seen_actions: list[str] = []
    claim_files: list[str] = []
    dependent_count = 0
    for spec, sequence in zip(_SEQUENCE_SPECS, root["sequences"]):
        expected_keys = {
            "sequence_id",
            "purpose",
            "temperature_bin_id",
            "session_canonical_sha256",
            "power_mode",
            "requires_controller_fresh_boot",
            "requires_panel_power_cycle",
            "j2_may_remain_on_before_session",
            "automatic_advance",
            "actions",
        }
        _exact(sequence, label=f"sequence {sequence['sequence_id']}", keys=expected_keys)
        if (
            sequence["purpose"] != spec["purpose"]
            or sequence["power_mode"] != spec["power_mode"]
            or sequence["temperature_bin_id"] != spec["temperature_bin_id"]
            or sequence["requires_panel_power_cycle"] is not False
            or sequence["j2_may_remain_on_before_session"] is not True
            or sequence["automatic_advance"] is not False
        ):
            raise N8CampaignError("N8 sequence session semantics changed")
        expected_fresh = spec["power_mode"] == "controller_fresh_boot"
        if sequence["requires_controller_fresh_boot"] is not expected_fresh:
            raise N8CampaignError("N8 controller boot semantics changed")
        session = p0_sessions.get(sequence["sequence_id"])
        if session is None:
            raise N8CampaignError("N8 sequence has no P0 session")
        if (
            session["integrity"]["canonical_sha256"]
            != sequence["session_canonical_sha256"]
            or session["power_mode"] != sequence["power_mode"]
            or session["automatic_advance"] is not False
        ):
            raise N8CampaignError("N8 outer/P0 session binding changed")
        records = sequence["actions"]
        if not isinstance(records, list) or len(records) != len(spec["steps"]):
            raise N8CampaignError("N8 sequence action count changed")
        prior_sha: Optional[str] = None
        for ordinal, ((role, source_id), record) in enumerate(
            zip(spec["steps"], records), start=1
        ):
            _exact(
                record,
                label=f"sequence action {sequence['sequence_id']}:{ordinal}",
                keys={
                    "ordinal",
                    "role",
                    "frame_source_id",
                    "frame_sha256",
                    "action_identity_sha256",
                    "claim_declaration",
                    "prior_result_requirement",
                },
            )
            action_sha = _require_sha256(
                record["action_identity_sha256"],
                label="N8 action identity",
            )
            assert action_sha is not None
            action = p0_actions.get(action_sha)
            if action is None:
                raise N8CampaignError("N8 sequence references an unknown P0 action")
            if (
                record["ordinal"] != ordinal
                or record["role"] != role
                or record["frame_source_id"] != source_id
                or record["frame_sha256"] != root["frames"][source_id]["frame"]["sha256"]
                or action["identity"]["frame"]["sha256"] != record["frame_sha256"]
                or action["claim"] != record["claim_declaration"]
            ):
                raise N8CampaignError("N8 action/frame/claim binding changed")
            identity = action["identity"]
            if (
                identity["session_id"] != sequence["sequence_id"]
                or identity["cell_id"] != sequence["sequence_id"]
                or identity["action_id"]
                != f"{sequence['sequence_id']}-{role.lower()}"
                or identity["phase"] != role.lower()
                or identity["request"]["method"] != "POST"
                or identity["request"]["endpoint"] != "/api/frame"
                or identity["request"]["maximum_post_requests"] != 1
                or identity["automatic_retry"] is not False
                or identity["automatic_recovery"] is not False
            ):
                raise N8CampaignError("N8 exact P0 action contract changed")
            requirement = _exact(
                record["prior_result_requirement"],
                label="N8 prior result requirement",
                keys={
                    "required",
                    "reason",
                    "prior_action_identity_sha256",
                    "required_result_state",
                    "required_result_file_sha256",
                },
            )
            if prior_sha is None:
                if action["identity"]["prior"] is not None or requirement != {
                    "required": False,
                    "reason": "session-root-action-has-no-predecessor",
                    "prior_action_identity_sha256": None,
                    "required_result_state": None,
                    "required_result_file_sha256": None,
                }:
                    raise N8CampaignError("N8 session root dependency changed")
            else:
                dependent_count += 1
                if action["identity"]["prior"] != {
                    "action_identity_sha256": prior_sha,
                    "scope": "same_cell",
                    "required_result_state": ResultState.PASS.value,
                }:
                    raise N8CampaignError("N8 action is not chained to its immediate predecessor")
                if requirement != {
                    "required": True,
                    "reason": "bind-exact-whole-file-result-before-description",
                    "prior_action_identity_sha256": prior_sha,
                    "required_result_state": ResultState.PASS.value,
                    "required_result_file_sha256": None,
                }:
                    raise N8CampaignError("N8 prior PASS whole-file binding contract changed")
            seen_actions.append(action_sha)
            claim_files.append(action["claim"]["filename"])
            prior_sha = action_sha
        if session["action_identity_sha256s"] != [
            record["action_identity_sha256"] for record in records
        ]:
            raise N8CampaignError("N8 P0 session action order changed")
    if (
        len(seen_actions) != 15
        or len(set(seen_actions)) != 15
        or set(seen_actions) != set(p0_actions)
        or len(set(claim_files)) != 15
        or dependent_count != 10
    ):
        raise N8CampaignError("N8 action/claim/dependency uniqueness changed")
    if root["power_semantics"] != _power_semantics():
        raise N8CampaignError("N8 power semantics changed")
    if root["dependency_contract"] != {
        "session_root_actions": 5,
        "dependent_actions_requiring_exact_prior_pass_result_file_sha256": 10,
        "required_state": ResultState.PASS.value,
        "binding_time": "describe-or-plan-before-each-dependent-action",
        "root_exception": (
            "a DAG root has no predecessor; every non-root visible action requires "
            "the immediately preceding whole result file SHA-256 and PASS state"
        ),
        "cross_sequence_result_binding_allowed": False,
    }:
        raise N8CampaignError("N8 dependency contract changed")
    if root["scheduler_contract"] != {
        "mode": "describe-plan-only",
        "automatic_advance": False,
        "unattended_operation": False,
        "claim_creation": False,
        "authorization_creation": False,
        "execution_runner_present": False,
        "abnormal_terminal_state": ResultState.UNKNOWN_DO_NOT_RETRY.value,
        "remaining_actions_stop_after_abnormality": True,
    }:
        raise N8CampaignError("N8 scheduler contract changed")
    if root["analysis_contract"] != _analysis_contract():
        raise N8CampaignError("N8 descriptive-only analysis contract changed")
    classification = root["classification"]
    if classification != {
        "offline_compiled": True,
        "software_ready": True,
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "automatic_execution": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "claim_created": False,
        "authorization_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
    }:
        raise N8CampaignError("N8 offline classification changed")
    if root["hardware_readiness"]["ready"] is not False:
        raise N8CampaignError("offline N8 manifest cannot be hardware-ready")
    if (
        root["hardware_readiness"]["internal_temperature_available"] is not False
        or root["hardware_readiness"]["swc_temperature_available"] is not False
        or root["hardware_readiness"]["inference_from_internal_or_swc_forbidden"] is not True
    ):
        raise N8CampaignError("N8 temperature availability statement changed")
    expected_blockers = list(
        dict.fromkeys(
            [
                *_binding_blockers(
                    panel=root["panel"],
                    firmware=root["firmware"],
                    profile=root["limit_profile"],
                    bindings=root["binding_registry"],
                ),
                *_measurement_blockers(root["measurement_registry"]),
                *_temperature_bin_blockers(root["temperature_bin_plan"]),
                "limit_profile_validity_and_usage_not_evaluated",
                "current_external_temperature_measurement_not_supplied",
                "current_electrical_and_operator_gates_not_evaluated",
                "exact_action_authorization_not_supplied",
            ]
        )
    )
    if root["hardware_readiness"]["blockers"] != expected_blockers:
        raise N8CampaignError("N8 hardware blocker list is not derived from its evidence")
    if root["compiler_effects"] != {
        "visible_action_declarations": 15,
        "workspace_global_claim_declarations": 15,
        "sessions": 5,
        "dependent_prior_result_bindings": 10,
        "claims_created": 0,
        "authorizations_created": 0,
        "network_requests": 0,
        "device_operations": 0,
        "visible_refreshes": 0,
    }:
        raise N8CampaignError("N8 compiler side-effect accounting changed")
    return root


def _sequence_for_action(
    manifest: Mapping[str, Any], action_identity_sha256: str
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    matches = [
        (sequence, action)
        for sequence in manifest["sequences"]
        for action in sequence["actions"]
        if action["action_identity_sha256"] == action_identity_sha256
    ]
    if len(matches) != 1:
        raise N8CampaignError("action is not uniquely bound to an N8 sequence")
    return matches[0]


def describe_n8_action(
    manifest: Mapping[str, Any],
    *,
    action_identity_sha256: str,
    evaluated_at: str,
    limit_profile: Optional[Mapping[str, Any]] = None,
    prior_result: Optional[Mapping[str, Any]] = None,
    prior_result_sha256: Optional[str] = None,
) -> dict[str, Any]:
    """Describe one action and exact predecessor binding with zero I/O."""

    root = validate_n8_manifest(manifest)
    sequence, action_record = _sequence_for_action(root, action_identity_sha256)
    selected_profile = root["limit_profile"] if limit_profile is None else limit_profile
    try:
        p0_description = describe_action_offline(
            root["p0_campaign"],
            action_identity_sha256=action_identity_sha256,
            limit_profile=selected_profile,
            evaluated_at=evaluated_at,
            prior_result=prior_result,
            prior_result_sha256=prior_result_sha256,
        )
    except CampaignContractError as error:
        raise N8CampaignError(f"P0 action description failed: {error}") from error
    extra_blockers = [
        *_binding_blockers(
            panel=root["panel"],
            firmware=root["firmware"],
            profile=selected_profile,
            bindings=root["binding_registry"],
        ),
        *_measurement_blockers(root["measurement_registry"]),
        *_temperature_bin_blockers(root["temperature_bin_plan"]),
        "current_external_temperature_measurement_not_supplied_to_offline_planner",
        "current_electrical_and_operator_gates_not_evaluated",
        "exact_action_authorization_not_supplied",
    ]
    blockers = list(dict.fromkeys([*p0_description["blockers"], *extra_blockers]))
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": DESCRIPTION_KIND,
        "mode": "describe-only",
        "campaign_id": CAMPAIGN_ID,
        "manifest_canonical_sha256": root["integrity"]["canonical_sha256"],
        "sequence_id": sequence["sequence_id"],
        "action_record": _snapshot(action_record),
        "p0_description": p0_description,
        "offline_contract_ready": p0_description["contract_ready"] and not extra_blockers,
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "claim_created": False,
        "authorization_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "automatic_advance": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "blockers": blockers,
    }
    return {**unsigned, "integrity": _integrity(unsigned, DESCRIPTION_HASH_SCOPE)}


def describe_n8_schedule(
    manifest: Mapping[str, Any],
    *,
    sequence_id: str,
    evaluated_at: str,
    result_bindings: Optional[Mapping[str, Mapping[str, Any]]] = None,
    limit_profile: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Plan only the next explicit step; never advance or execute it."""

    root = validate_n8_manifest(manifest)
    matches = [value for value in root["sequences"] if value["sequence_id"] == sequence_id]
    if len(matches) != 1:
        raise N8CampaignError("requested sequence is not uniquely present")
    sequence = matches[0]
    bindings = {} if result_bindings is None else dict(result_bindings)
    action_shas = [record["action_identity_sha256"] for record in sequence["actions"]]
    foreign = sorted(set(bindings) - set(action_shas))
    if foreign:
        raise N8CampaignError("result binding crosses an N8 sequence")

    completed: list[dict[str, Any]] = []
    abnormal: Optional[dict[str, Any]] = None
    gap_seen = False
    for ordinal, action_sha in enumerate(action_shas, start=1):
        binding = bindings.get(action_sha)
        if binding is None:
            gap_seen = True
            continue
        if gap_seen:
            raise N8CampaignError("result bindings are not a contiguous sequence prefix")
        record = _exact(
            binding,
            label=f"result binding {action_sha}",
            keys={"result", "result_file_sha256"},
        )
        try:
            result = validate_result_record(record["result"])
            actual_sha = result_file_sha256(result)
        except CampaignContractError as error:
            raise N8CampaignError(f"result binding is invalid: {error}") from error
        supplied_sha = _require_sha256(
            record["result_file_sha256"],
            label="bound result whole-file SHA-256",
        )
        if supplied_sha != actual_sha:
            raise N8CampaignError("bound result whole-file SHA-256 does not match")
        if result["action_identity_sha256"] != action_sha:
            raise N8CampaignError("bound result belongs to another action")
        completed.append(
            {
                "ordinal": ordinal,
                "action_identity_sha256": action_sha,
                "result_file_sha256": actual_sha,
                "state": result["state"],
            }
        )
        if result["state"] != ResultState.PASS.value:
            abnormal = completed[-1]
            if len(bindings) != len(completed):
                raise N8CampaignError("a result was recorded after an abnormal terminal action")
            break

    next_description: Optional[dict[str, Any]] = None
    next_sha: Optional[str] = None
    terminal_state: Optional[str] = None
    stop_remaining = False
    if abnormal is not None:
        terminal_state = ResultState.UNKNOWN_DO_NOT_RETRY.value
        stop_remaining = True
    elif len(completed) == len(action_shas):
        terminal_state = ResultState.PASS.value
    else:
        next_sha = action_shas[len(completed)]
        if completed:
            predecessor_sha = action_shas[len(completed) - 1]
            predecessor = bindings[predecessor_sha]
            next_description = describe_n8_action(
                root,
                action_identity_sha256=next_sha,
                evaluated_at=evaluated_at,
                limit_profile=limit_profile,
                prior_result=predecessor["result"],
                prior_result_sha256=predecessor["result_file_sha256"],
            )
        else:
            next_description = describe_n8_action(
                root,
                action_identity_sha256=next_sha,
                evaluated_at=evaluated_at,
                limit_profile=limit_profile,
            )
    remaining = action_shas[len(completed) :]
    if stop_remaining:
        remaining = []
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "mode": "describe-plan-only",
        "manifest_canonical_sha256": root["integrity"]["canonical_sha256"],
        "sequence_id": sequence_id,
        "completed_result_bindings": completed,
        "next_action_identity_sha256": next_sha,
        "next_action_description": next_description,
        "remaining_action_identity_sha256s": remaining,
        "terminal_state": terminal_state,
        "stop_remaining_actions": stop_remaining,
        "automatic_advance": False,
        "unattended_operation": False,
        "claim_created": False,
        "authorization_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
    }
    return {**unsigned, "integrity": _integrity(unsigned, PLAN_HASH_SCOPE)}


def describe_panel_cold_variant(
    manifest: Mapping[str, Any],
    *,
    evaluated_at: str,
    minimum_measured_panel_off_seconds: int | float,
    limit_profile: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Describe, but do not build, a panel-cold variant after profile review."""

    root = validate_n8_manifest(manifest)
    seconds = _number(
        minimum_measured_panel_off_seconds,
        label="minimum_measured_panel_off_seconds",
        minimum=0,
    )
    if seconds is None or seconds <= 0:
        raise N8CampaignError("panel-cold description requires a positive measured off interval")
    selected_profile = root["limit_profile"] if limit_profile is None else limit_profile
    try:
        decision = evaluate_limit_profile(selected_profile, evaluated_at=evaluated_at)
    except CampaignContractError as error:
        raise N8CampaignError(f"panel-cold limit profile is invalid: {error}") from error
    review = validate_limit_profile(selected_profile)["review"]
    blockers = list(decision.reasons)
    if review["approved"] is not True:
        blockers.append("panel_cold_requires_reviewed_profile")
    blockers.extend(
        _binding_blockers(
            panel=root["panel"],
            firmware=root["firmware"],
            profile=selected_profile,
            bindings=root["binding_registry"],
        )
    )
    blockers.extend(
        [
            "distinct_panel_cold_p0_session_not_compiled",
            "current_runtime_gates_and_exact_authorization_not_evaluated",
        ]
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": PANEL_COLD_DESCRIPTION_KIND,
        "mode": "describe-only",
        "manifest_canonical_sha256": root["integrity"]["canonical_sha256"],
        "power_mode": "panel_cold_cycle",
        "requires_controller_fresh_boot": True,
        "requires_panel_power_cycle": True,
        "j2_may_remain_on_before_session": False,
        "minimum_measured_panel_off_seconds": seconds,
        "review_artifact_sha256": review["review_artifact_sha256"],
        "profile_decision": decision.to_dict(),
        "contract_ready": False,
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "automatic_advance": False,
        "claim_created": False,
        "authorization_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "blockers": list(dict.fromkeys(blockers)),
    }
    return {**unsigned, "integrity": _integrity(unsigned, DESCRIPTION_HASH_SCOPE)}


def manifest_file_sha256(manifest: Mapping[str, Any]) -> str:
    return _sha256(validate_n8_manifest(manifest))


def frozen_manifest_bytes() -> bytes:
    """Return a canonical, round-trip deep-validated frozen N8 bundle."""

    manifest = compile_n8_manifest()
    payload = canonical_json_bytes(manifest)
    if _sha256(payload) != EXPECTED_FROZEN_MANIFEST_FILE_SHA256:
        raise N8CampaignError("frozen N8 bundle whole-file identity changed")
    try:
        round_trip = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N8CampaignError("frozen N8 bundle is not canonical JSON") from error
    validate_n8_manifest(round_trip)
    if canonical_json_bytes(round_trip) != payload:
        raise N8CampaignError("frozen N8 bundle is not byte-stable after round trip")
    return payload


def parse_rfc3339(value: str) -> datetime:
    """Validate an explicit timestamp for callers constructing offline evidence."""

    if not isinstance(value, str):
        raise N8CampaignError("timestamp must be RFC3339 text")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise N8CampaignError("timestamp must be RFC3339 text") from error
    if parsed.tzinfo is None:
        raise N8CampaignError("timestamp must include a timezone")
    return parsed
