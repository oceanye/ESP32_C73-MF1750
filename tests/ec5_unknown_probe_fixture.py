"""Local-only fixtures for the focused EC5 campaign/analyzer tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from tools import mf1750_ec5_unknown_probe_analyzer as analyzer
from tools import mf1750_ec5_unknown_probe_campaign as campaign


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_bytes(campaign.canonical_json_bytes(value))


def make_inputs(tmp_path: Path) -> dict[str, Any]:
    panel = {
        "model": "MF-1750",
        "serial": "MF1750-20260809-001",
        "board_id": "C73-DRIVER-001",
        "pcb_revision": "C73-R1",
    }
    firmware_payload = b"isolated-ec5-u04-white-pilot-firmware-fixture\x00\x04"
    build = {
        "schema_version": 1,
        "kind": campaign.BUILD_SIDECAR_KIND,
        "candidate_id": "U04",
        "candidate_code": 4,
        "build_tag": "ec5-u04-white-pilot-20260809",
        "firmware_commit": "a" * 40,
        "git_dirty": False,
        "binary_sha256": hashlib.sha256(firmware_payload).hexdigest(),
        "config_sha256": digest("ec5-u04-config"),
        "driver_baseline_commit": "b" * 40,
        "command_sequence_digest": digest("frozen-command-sequence"),
        "otp_mode": "factory-otp-unchanged",
        "created_at": "2026-08-09T12:00:00+08:00",
        "review_id": "ec5-u04-review-001",
        "manifest_payload_sha256": "0" * 64,
        "isolation": {
            "single_candidate_binary": True,
            "embedded_candidate_codes": [4],
            "candidate_fixture_count": 1,
            "contains_u07_fixture": False,
            "formal_six_color_guard_unchanged": True,
            "arbitrary_unknown_input_enabled": False,
            "unknown_spi_command_added": False,
            "waveform_modified": False,
        },
    }
    build["manifest_payload_sha256"] = campaign.sha256(
        campaign.build_fixture_manifest_payload(build)
    )
    panel_path = tmp_path / "panel.json"
    build_path = tmp_path / "build.json"
    firmware_path = tmp_path / "firmware.bin"
    write_json(panel_path, panel)
    write_json(build_path, build)
    firmware_path.write_bytes(firmware_payload)
    compiled = campaign.compile_campaign(panel_path, build_path, firmware_path)
    campaign_path = tmp_path / "campaign.json"
    write_json(campaign_path, compiled)
    action = compiled["actions"][0]
    binding = compiled["physical_binding"]
    observation = {
        "schema_version": 1,
        "kind": analyzer.OBSERVATION_KIND,
        "observation_id": "ec5-u04-observation-001",
        "observed_at": "2026-08-09T20:10:00+08:00",
        "test_id": campaign.TEST_ID,
        "candidate_code": campaign.U04_CODE,
        "intended_initial_code": campaign.WHITE_CODE,
        "campaign_canonical_sha256": compiled["integrity"]["canonical_sha256"],
        "action_identity_sha256": action["action_identity_sha256"],
        "manual_observation_contract_sha256": compiled[
            "manual_observation_contract"
        ]["canonical_sha256"],
        "lineage": {
            "panel_file_sha256": binding["panel_file_sha256"],
            "build_sidecar_sha256": binding["build_sidecar_sha256"],
            "firmware_binary_sha256": binding["firmware_binary_sha256"],
            "fixture_manifest_payload_sha256": compiled["fixture_manifest"][
                "manifest_payload_sha256"
            ],
            "measured_initial_record_id": "white-initial-measurement-001",
            "measured_initial_record_sha256": digest("white-initial-record"),
            "measurement_setup_sha256": digest("measurement-setup"),
            "cold_start_evidence_id": "cold-start-evidence-001",
            "user_authorization_id": "user-authorization-001",
            "device_report_id": "ec5-u04-device-report-001",
            "device_report_sha256": digest("device-report"),
        },
        "roi_observations": [
            {
                "roi_id": "ec5-cs1-unknown",
                "controller": "CS1",
                "classification": "other-stable",
                "stable_for_entire_observation": True,
                "notes": "left ROI visually stable",
            },
            {
                "roi_id": "ec5-cs2-unknown",
                "controller": "CS2",
                "classification": "other-stable",
                "stable_for_entire_observation": True,
                "notes": "right ROI visually stable",
            },
        ],
        "hold": {
            "start_at": "2026-08-09T20:00:00+08:00",
            "end_at": "2026-08-09T20:10:00+08:00",
            "duration_seconds": 600.0,
            "continuous_observation": True,
        },
        "electrical": {
            "psu_mode": "CV",
            "idle_current_a": 0.001,
            "peak_current_a": 0.42,
            "current_within_reviewed_gate": True,
            "rails_within_reviewed_gate": True,
            "cutoff_available": True,
            "abnormal_event_observed": False,
            "notes": "manual PSU and rail review normal",
        },
        "temperature": {
            "start_c": 24.0,
            "max_c": 27.5,
            "end_c": 26.0,
            "within_reviewed_gate": True,
            "unexplained_hotspot": False,
            "notes": "manual temperature review normal",
        },
        "esp_continuity": {
            "boot_id_before": "boot-20260809-001",
            "boot_id_after": "boot-20260809-001",
            "reset_observed": False,
            "same_boot_continuity": True,
            "job_continuity_observed": True,
            "notes": "ESP remained on the same boot",
        },
        "anomaly_review": {
            "visual_damage_or_crack": False,
            "controller_divergence_worsening": False,
            "busy_anomaly": False,
            "odor_smoke_arc_or_noise": False,
            "evidence_missing": False,
            "notes": "no manually observed stop condition",
        },
        "notes": "single descriptive U04 white-initial pilot observation",
    }
    observation_path = tmp_path / "observation.json"
    write_json(observation_path, observation)
    return {
        "panel": panel,
        "panel_path": panel_path,
        "build": build,
        "build_path": build_path,
        "firmware_payload": firmware_payload,
        "firmware_path": firmware_path,
        "campaign": compiled,
        "campaign_path": campaign_path,
        "observation": observation,
        "observation_path": observation_path,
    }
