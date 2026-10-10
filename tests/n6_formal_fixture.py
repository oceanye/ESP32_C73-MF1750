"""Synthetic test-only fixtures for the strict N6 formal execution layer."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
from io import BytesIO
from typing import Any, Mapping

from host.application import (
    InputSource,
    SimulationOptions,
    decode_normalized_source,
    prepare_simulation_artifact,
    simulate_panel,
)
from host.application.n6_browser_campaign import build_n6_offline_manifest
from host.application.n6_visible_execution import (
    AUTHORIZATION_KIND,
    FORMAL_ARTIFACT_REVIEW_KIND,
    N6_ARM_CONFIRMATION,
    RUNTIME_OBSERVATION_KIND,
    RUNTIME_REVIEW_KIND,
    materialize_n6_formal_manifest,
    seal_n6_external_authorization,
    seal_n6_formal_artifact_review,
    seal_n6_runtime_observation,
    seal_n6_runtime_review,
)
from host.color_pipeline import CalibrationProvenance, Palette, reference_palette
from host.extended_color.aggregation import (
    CANONICAL_HASH_SCOPE as AGGREGATE_HASH_SCOPE,
    PALETTE_AGGREGATE_KIND,
    PALETTE_PLAN_KIND,
)
from host.epd_frame import fnv1a
from host.gamut_mapping import (
    build_synthetic_reference_profile,
    gamut_profile_from_mapping,
    seal_profile_mapping,
)
from host.visible_refresh_campaign import (
    ResultState,
    build_result_record,
    canonical_json_bytes,
    result_file_sha256,
    seal_limit_profile,
)
from tests.application_browser_harness import TEST_BUILD_TAG, TEST_DRIVER_API


SOURCE_COMMIT = "1" * 40
APPLICATION_BUILD_SHA256 = "2" * 64
PANEL = {
    "model": "MF-17506-M009F-T",
    "serial": "N6-TEST-PANEL-001",
    "board_id": "N6-TEST-BOARD-001",
    "pcb_revision": "test-only",
}
FIRMWARE = {
    "source_commit": SOURCE_COMMIT,
    "build_tag": TEST_BUILD_TAG,
    "binary_sha256": "3" * 64,
    "driver_api": TEST_DRIVER_API,
}
MATERIALIZED_AT = "2026-08-08T12:30:00+08:00"
CLAIMED_AT = "2026-08-08T12:40:00+08:00"
COMPLETED_AT = "2026-08-08T12:41:00+08:00"


def _integrity(unsigned: Mapping[str, Any]) -> dict[str, str]:
    return {
        "canonical_sha256": hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest(),
        "canonical_sha256_scope": AGGREGATE_HASH_SCOPE,
    }


@lru_cache(maxsize=1)
def measured_palette() -> Palette:
    reference = reference_palette()
    return Palette(
        "n6-test-measured-palette",
        reference.entries,
        True,
        "synthetic structural test only",
        calibration=CalibrationProvenance("n6-test-measurement", "4" * 64),
    )


@lru_cache(maxsize=1)
def palette_aggregate() -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "kind": PALETTE_AGGREGATE_KIND,
        "plan_kind": PALETTE_PLAN_KIND,
        "plan_canonical_sha256": "5" * 64,
        "expected_sample_count": 36,
        "accepted_sample_count": 36,
        "missing_slot_ids": [],
        "blockers": [],
        "statistics": {},
        "percentile_rule": "n<10 uses maximum_observed plus U95; P95/P99 are null",
        "palette": measured_palette().canonical_mapping(),
        "classification": {
            "measured": True,
            "calibrated": True,
            "hardware_execution_authorized": False,
            "claim_created": False,
            "authorization_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
        },
    }
    return {**deepcopy(payload), "integrity": _integrity(payload)}


@lru_cache(maxsize=1)
def measured_gamut_profile() -> dict[str, Any]:
    palette = measured_palette()
    payload = build_synthetic_reference_profile(reference_palette()).canonical_mapping()
    payload.pop("canonical_sha256")
    payload["profile_id"] = "n6-test-measured-mixtures-v1"
    payload["palette"] = {
        "id": palette.palette_id,
        "canonical_sha256": palette.canonical_sha256,
    }
    payload["model"].update(
        {
            "kind": "measured_point_cloud_v1",
            "characterization_level": "measured_mixtures",
            "approximation": False,
            "mixture_samples": [
                {
                    "sample_id": "n6-test-mix-black-white",
                    "mask_id": "checker-2x2",
                    "area_fractions": [
                        {"code": 0, "fraction": 0.5},
                        {"code": 1, "fraction": 0.5},
                    ],
                    "xyz": [0.45, 0.5, 0.54],
                    "artifact_sha256": "6" * 64,
                }
            ],
        }
    )
    for index, item in enumerate(payload["model"]["pure_sample_refs"]):
        item["artifact_sha256"] = f"{index + 10:064x}"
    payload["measurement"].update(
        {
            "measurement_id": "n6-test-gamut-measurement",
            "raw_artifact_sha256": "7" * 64,
            "geometry": "45/0",
            "backing": "white calibrated backing",
            "instrument": "structural-test-spectrophotometer",
            "instrument_calibration_date": "2026-01-01",
            "measured_at": "2026-08-08T10:00:00+08:00",
        }
    )
    payload["panel"].update(
        {"model": PANEL["model"], "panel_id": PANEL["serial"], "batch": "N6-TEST-BATCH"}
    )
    payload["firmware"].update(
        {"commit": SOURCE_COMMIT, "waveform_version": "n6-test-waveform-v1"}
    )
    payload["environment"].update(
        {
            "temperature_c": 25.0,
            "temperature_tolerance_c": 2.0,
            "relative_humidity_percent": 50.0,
        }
    )
    payload["trust"].update(
        {
            "source_statement": "synthetic structural N6 test evidence only",
            "signature": "test-only-not-a-production-signature",
        }
    )
    sealed = seal_profile_mapping(payload)
    gamut_profile_from_mapping(sealed, palette)
    return sealed


def source_png() -> bytes:
    from PIL import Image

    image = Image.new("RGB", (4, 2))
    image.putdata(
        [
            (240, 20, 20),
            (20, 180, 40),
            (30, 60, 220),
            (240, 220, 20),
            (20, 20, 20),
            (240, 240, 235),
            (220, 50, 40),
            (20, 150, 60),
        ]
    )
    output = BytesIO()
    image.save(output, format="PNG", optimize=False)
    return output.getvalue()


@lru_cache(maxsize=1)
def artifact_and_config():
    palette = measured_palette()
    profile = gamut_profile_from_mapping(measured_gamut_profile(), palette)
    source_bytes = source_png()
    decoded = decode_normalized_source(
        source_bytes, "image/png", "contain", rotation_degrees=0
    )
    simulation = simulate_panel(
        decoded.raster,
        palette=palette,
        profile=profile,
        options=SimulationOptions(algorithm="none"),
    )
    source = InputSource(
        "browser-selected-image",
        "image/png",
        hashlib.sha256(source_bytes).hexdigest(),
        "server-recomputed SHA256 of original selected file bytes",
    )
    artifact = prepare_simulation_artifact(
        simulation, source, decode_provenance=decoded.provenance
    )
    config = {
        "palette": {
            "id": palette.palette_id,
            "canonical_sha256": palette.canonical_sha256,
            "calibrated": True,
            "calibration": {
                "measurement_id": palette.calibration.measurement_id,
                "artifact_sha256": palette.calibration.artifact_sha256,
            },
        },
        "gamut_profiles": [
            {
                "id": profile.profile_id,
                "canonical_sha256": profile.canonical_sha256,
                "characterization_level": profile.characterization_level,
                "hardware_formal_qualified": False,
            }
        ],
        "formal_eligibility": {"eligible": False},
    }
    return artifact, config


@lru_cache(maxsize=1)
def offline_manifest() -> dict[str, Any]:
    artifact, config = artifact_and_config()
    return build_n6_offline_manifest(
        artifact,
        config,
        panel=PANEL,
        firmware=FIRMWARE,
        campaign_id="n6-test-formal-campaign",
        session_id="n6-test-formal-session",
        cell_id="n6-test-formal-cell",
        action_id="n6-test-formal-action",
    )


@lru_cache(maxsize=1)
def prior_result() -> dict[str, Any]:
    return build_result_record(
        action_identity_sha256="8" * 64,
        state=ResultState.PASS,
        completed_at="2026-08-08T11:00:00+08:00",
        evidence_manifest_sha256="9" * 64,
        post_request_count=1,
        details="test-only prior PASS",
    )


@lru_cache(maxsize=1)
def reviewed_limit_profile() -> dict[str, Any]:
    manifest = offline_manifest()
    payload = deepcopy(manifest["draft_limit_profile"])
    payload.pop("integrity")
    payload["profile_id"] = "n6-test-reviewed-limit"
    payload["limits"] = {
        "maximum_campaign_visible_refreshes": 100,
        "maximum_session_visible_refreshes": 10,
        "maximum_consecutive_visible_refreshes": 10,
        "minimum_interval_seconds": 0,
        "minimum_cooldown_seconds": 0,
        "minimum_start_temperature_c": 5.0,
        "maximum_start_temperature_c": 45.0,
        "maximum_post_refresh_temperature_c": 55.0,
    }
    payload["usage"] = {
        "cumulative_visible_refresh_count": 10,
        "session_visible_refresh_count": 1,
        "consecutive_visible_refresh_count": 1,
        "last_visible_refresh_completed_at": "2026-08-08T11:00:00+08:00",
        "snapshot_at": "2026-08-08T12:00:00+08:00",
        "evidence_sha256": "a" * 64,
    }
    payload["validity"] = {
        "valid_from": "2026-08-08T10:00:00+08:00",
        "expires_at": "2026-08-08T23:00:00+08:00",
    }
    payload["review"] = {
        "approved": True,
        "reviewer_id": "n6-test-limit-reviewer",
        "reviewed_at": "2026-08-08T09:00:00+08:00",
        "review_artifact_sha256": "b" * 64,
    }
    return seal_limit_profile(payload)


@lru_cache(maxsize=1)
def runtime_review() -> dict[str, Any]:
    return seal_n6_runtime_review(
        {
            "schema_version": 1,
            "kind": RUNTIME_REVIEW_KIND,
            "runtime_id": "n6-test-runtime",
            "application_build": {
                "source_commit": SOURCE_COMMIT,
                "bundle_sha256": APPLICATION_BUILD_SHA256,
            },
            "firmware": FIRMWARE,
            "browser_contract": {
                "loopback_only": True,
                "token_required": True,
                "same_origin_post_required": True,
                "server_recomputes_source_sha256": True,
                "convert_v2_required": True,
                "four_previews_required": True,
                "one_shot_arm_required": True,
                "reload_cannot_reset_claim_or_submission": True,
            },
            "device_contract": {
                "method": "POST",
                "endpoint": "/api/frame",
                "maximum_frame_posts": 1,
                "automatic_retry": False,
                "automatic_recovery": False,
                "cs1_mapping": {
                    "source_half": 0,
                    "flip_x": False,
                    "flip_y": False,
                    "nibble_swap": False,
                },
                "cs2_mapping": {
                    "source_half": 1,
                    "flip_x": False,
                    "flip_y": False,
                    "nibble_swap": False,
                },
                "minimum_controller_voltage_v": 3.2,
                "maximum_controller_voltage_v": 3.4,
                "maximum_idle_current_a": 0.01,
                "j2_must_be_on": True,
            },
            "review": {
                "approved": True,
                "reviewer_id": "n6-test-runtime-reviewer",
                "reviewed_at": "2026-08-08T09:05:00+08:00",
                "review_artifact_sha256": "c" * 64,
            },
        }
    )


@lru_cache(maxsize=1)
def formal_artifact_review() -> dict[str, Any]:
    manifest = offline_manifest()
    source = manifest["source_artifact"]
    profile = measured_gamut_profile()
    return seal_n6_formal_artifact_review(
        {
            "schema_version": 1,
            "kind": FORMAL_ARTIFACT_REVIEW_KIND,
            "review_id": "n6-test-artifact-review",
            "offline_manifest_canonical_sha256": manifest["integrity"][
                "canonical_sha256"
            ],
            "artifact_identity": source["artifact_identity"],
            "source_input_sha256": source["input"]["sha256"],
            "four_preview_sha256": {
                stage: source["previews"][stage]["sha256"]
                for stage in ("source", "mapped", "final", "model")
            },
            "palette_aggregate_canonical_sha256": palette_aggregate()["integrity"][
                "canonical_sha256"
            ],
            "palette_canonical_sha256": measured_palette().canonical_sha256,
            "gamut_profile_canonical_sha256": profile["canonical_sha256"],
            "panel": PANEL,
            "firmware": FIRMWARE,
            "application_build_sha256": APPLICATION_BUILD_SHA256,
            "review": {
                "approved": True,
                "reviewer_id": "n6-test-artifact-reviewer",
                "reviewed_at": "2026-08-08T09:10:00+08:00",
                "review_artifact_sha256": "d" * 64,
            },
        }
    )


@lru_cache(maxsize=1)
def formal_manifest() -> dict[str, Any]:
    prior = prior_result()
    return materialize_n6_formal_manifest(
        offline_manifest(),
        materialized_at=MATERIALIZED_AT,
        palette_aggregate=palette_aggregate(),
        gamut_profile=measured_gamut_profile(),
        formal_artifact_review=formal_artifact_review(),
        reviewed_limit_profile=reviewed_limit_profile(),
        runtime_review=runtime_review(),
        prior_result=prior,
        prior_result_sha256=result_file_sha256(prior),
    )


def authorization() -> dict[str, Any]:
    manifest = formal_manifest()
    return seal_n6_external_authorization(
        {
            "schema_version": 1,
            "kind": AUTHORIZATION_KIND,
            "authorization_id": "n6-test-one-visible-auth",
            "formal_manifest_canonical_sha256": manifest["integrity"][
                "canonical_sha256"
            ],
            "action_identity_sha256": manifest["action"]["action_identity_sha256"],
            "prior_result_file_sha256": manifest["prior_binding"][
                "result_file_sha256"
            ],
            "issued_at": "2026-08-08T12:35:00+08:00",
            "expires_at": "2026-08-08T13:00:00+08:00",
            "operator_id": "n6-test-operator",
            "authorization_artifact_sha256": "e" * 64,
            "confirmation_sha256": hashlib.sha256(
                N6_ARM_CONFIRMATION.encode("utf-8")
            ).hexdigest(),
            "maximum_frame_posts": 1,
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
        },
        manifest=manifest,
    )


def runtime_observation(origin: str = "http://127.0.0.1:8765") -> dict[str, Any]:
    manifest = formal_manifest()
    return seal_n6_runtime_observation(
        {
            "schema_version": 1,
            "kind": RUNTIME_OBSERVATION_KIND,
            "formal_manifest_canonical_sha256": manifest["integrity"][
                "canonical_sha256"
            ],
            "observed_at": "2026-08-08T12:39:00+08:00",
            "controller_voltage_v": 3.3,
            "idle_current_a": 0.001,
            "start_temperature_c": 25.0,
            "supply_3v3_normal": True,
            "supply_cv_current_normal": True,
            "j2_on": True,
            "physical_cutoff_available": True,
            "operator_present": True,
            "application_origin": origin,
            "operator_gate_artifact_sha256": "f" * 64,
            "runtime_evidence_sha256": "1" * 64,
        },
        manifest=manifest,
    )


def browser_observation() -> dict[str, Any]:
    artifact, _ = artifact_and_config()
    payload = {
        "source_conversion_bound": True,
        "source_input_sha256": artifact.report["input"]["sha256"],
        "artifact_report_sha256": artifact.identity["report_sha256"],
        "preview_stages_verified": ["source", "mapped", "final", "model"],
        "page_load_count": 1,
        "reload_count": 0,
        "token_validated": True,
        "same_origin_mutations_validated": True,
        "local_preflight_only": True,
        "one_shot_arm_count": 1,
        "execute_request_count": 1,
    }
    payload["browser_evidence_sha256"] = hashlib.sha256(
        canonical_json_bytes(payload)
    ).hexdigest()
    return payload


def success_protocol_result() -> dict[str, Any]:
    manifest = formal_manifest()
    artifact, _ = artifact_and_config()
    action = manifest["action"]
    job = {
        "job_id": 73,
        "action": "uploaded_frame",
        "state": "completed",
        "result": True,
        "queued_at_ms": 100,
        "started_at_ms": 101,
        "finished_at_ms": 200,
        "frame_fnv1a": fnv1a(artifact.frame),
    }
    return {
        "mode": "refresh",
        "protocol_verified": True,
        "hardware_tested": False,
        "verified_scope": ["test-only-deep-validated-by-N6"],
        "manual_observation_required": [
            "full_panel_visual_result",
            "power_supply_cv_and_current",
            "L1_L2_temperature",
        ],
        "preflight": {
            "build_tag": FIRMWARE["build_tag"],
            "driver_api": FIRMWARE["driver_api"],
            "panel": "1024x600",
            "frame_bytes": 307200,
            "psram_bytes": 8388608,
            "free_psram": 7900000,
            "refresh_spi_hz": 1000000,
            "controller_mappings": [
                {
                    "controller": "CS1",
                    "mapping": action["identity"]["frame"]["controllers"][0][
                        "mapping"
                    ],
                },
                {
                    "controller": "CS2",
                    "mapping": action["identity"]["frame"]["controllers"][1][
                        "mapping"
                    ],
                },
            ],
        },
        "job_id": 73,
        "job": job,
        "diagnostic": {
            "operation_id": 73,
            "job_operation_id": 73,
            "job_driver_operation_identity_matched": True,
            "sequence_verified": True,
            "required_busy_stages_verified": True,
            "post_psr_busy_seen": False,
            "busy_timeout": False,
            "safe_finish_verified": True,
            "busy_trace": None,
            "physical_controllers": [
                {
                    "controller": item["controller"],
                    "mapping": item["mapping"],
                    "dtm_bytes": item["dtm_bytes"],
                    "dtm_fnv1a": int(item["dtm_fnv1a"][2:], 16),
                }
                for item in action["identity"]["frame"]["controllers"]
            ],
        },
        "frame_post_request_count": 1,
    }


__all__ = [
    "CLAIMED_AT",
    "COMPLETED_AT",
    "FIRMWARE",
    "MATERIALIZED_AT",
    "PANEL",
    "artifact_and_config",
    "authorization",
    "browser_observation",
    "formal_manifest",
    "offline_manifest",
    "runtime_observation",
    "source_png",
    "success_protocol_result",
]
