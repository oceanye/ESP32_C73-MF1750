"""Test-only builder for canonical N3 finalized action bundle pairs."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping, Optional
from unittest import mock

from PIL import Image

from host.visible_refresh_campaign import (
    LIMIT_PROFILE_KIND,
    ResultState,
    canonical_json_bytes,
    seal_limit_profile,
)
from tests.test_frame_tool import ScriptedRequester
from tests.test_g1_s1_rc2g_map_baseline_once import (
    TickClock as MapTickClock,
    _responses as map_responses,
)
from tests.test_g1_s1_rc2g_quality_refresh_once import (
    TickClock as TargetTickClock,
    _responses as target_responses,
)
from tools import g1_s1_n3_campaign as planning
from tools import g1_s1_n3_execution_contract as execution
from tools import g1_s1_rc2g_n3_once as runner


EVALUATED_AT = "2026-08-08T00:00:15Z"
TARGET_EVALUATED_AT = "2026-08-08T00:02:00Z"
MAP_OBSERVED_AT = "2026-08-08T00:01:00Z"
TARGET_OBSERVED_AT = "2026-08-08T00:03:00Z"


def fixture_sha256(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def registered_assets() -> dict[str, Any]:
    return planning.build_measurement_asset_registry(
        timing_clock_asset_sha256=fixture_sha256("n3-clock-v1"),
        temperature_sensor_asset_sha256=fixture_sha256("n3-temperature-sensor-v1"),
        temperature_calibration_asset_sha256=fixture_sha256(
            "n3-temperature-calibration-v1"
        ),
        temperature_location_asset_sha256=fixture_sha256(
            "n3-temperature-location-v1"
        ),
        camera_body_asset_sha256=fixture_sha256("n3-camera-body-v1"),
        camera_lens_asset_sha256=fixture_sha256("n3-camera-lens-v1"),
        camera_mount_asset_sha256=fixture_sha256("n3-camera-mount-v1"),
        camera_capture_config_sha256=fixture_sha256("n3-camera-config-v1"),
        camera_crop_asset_sha256=fixture_sha256("n3-camera-crop-v1"),
        illumination_asset_sha256=fixture_sha256("n3-illumination-v1"),
    )


def _write_json(path: Path, value: Mapping[str, Any]) -> Path:
    path.write_bytes(canonical_json_bytes(value))
    return path


def _profile(campaign: Mapping[str, Any], *, prior_completed: bool) -> dict[str, Any]:
    allowlist = []
    for action in campaign["actions"]:
        identity = action["identity"]
        allowlist.append(
            {
                "action_id": identity["action_id"],
                "action_identity_sha256": action["action_identity_sha256"],
                "method": "POST",
                "endpoint": "/api/frame",
                "frame_sha256": identity["frame"]["sha256"],
                "maximum_uses": 1,
            }
        )
    return seal_limit_profile(
        {
            "schema_version": 1,
            "kind": LIMIT_PROFILE_KIND,
            "profile_id": "n3-test-only-reviewed-profile",
            "profile_version": "1.0.0",
            "panel": dict(campaign["panel"]),
            "firmware": dict(campaign["firmware"]),
            "action_allowlist": allowlist,
            "limits": {
                "maximum_campaign_visible_refreshes": len(campaign["actions"]),
                "maximum_session_visible_refreshes": 2,
                "maximum_consecutive_visible_refreshes": 2,
                "minimum_interval_seconds": 0,
                "minimum_cooldown_seconds": 0,
                "minimum_start_temperature_c": 10,
                "maximum_start_temperature_c": 40,
                "maximum_post_refresh_temperature_c": 45,
            },
            "usage": {
                "cumulative_visible_refresh_count": 1 if prior_completed else 0,
                "session_visible_refresh_count": 1 if prior_completed else 0,
                "consecutive_visible_refresh_count": 1 if prior_completed else 0,
                "last_visible_refresh_completed_at": (
                    MAP_OBSERVED_AT if prior_completed else None
                ),
                "snapshot_at": (
                    "2026-08-08T00:01:30Z"
                    if prior_completed
                    else "2026-08-08T00:00:00Z"
                ),
                "evidence_sha256": fixture_sha256("n3-usage-evidence"),
            },
            "validity": {
                "valid_from": "2026-08-08T00:00:00Z",
                "expires_at": "2026-09-01T00:00:00Z",
            },
            "review": {
                "approved": True,
                "reviewer_id": "n3-test-reviewer",
                "reviewed_at": "2026-08-07T23:00:00Z",
                "review_artifact_sha256": fixture_sha256("n3-review-artifact"),
            },
        }
    )


def _materialize_bundle(
    root: Path, registry: Path, bundle: Mapping[str, Any]
) -> Path:
    directory = root / "materialized-prior"
    directory.mkdir()
    registry.mkdir(exist_ok=True)
    filenames = {
        "lock": runner.LOCK_FILENAME,
        "profile": runner.PROFILE_FILENAME,
        "evidence": runner.EVIDENCE_FILENAME,
        "observation": runner.OBSERVATION_FILENAME,
        "finalization": runner.FINALIZATION_FILENAME,
        "result": runner.P0_RESULT_FILENAME,
    }
    for key, filename in filenames.items():
        _write_json(directory / filename, bundle[key])
    claim_filename = bundle["evidence"]["claim"]["filename"]
    _write_json(registry / claim_filename, bundle["claim"])
    return directory / runner.P0_RESULT_FILENAME


def _operator_observation(
    snapshot: execution.N3ActionSnapshot,
    *,
    root: Path,
    state: ResultState,
    metric_offset: float,
    overrides: Optional[Mapping[str, Any]],
) -> dict[str, Any]:
    target = snapshot.phase == "target"
    if target:
        visual: dict[str, Any] = {
            "target_fidelity_pass": state is ResultState.PASS,
            "orientation_pass": True,
            "seam_assessment_pass": True,
            "full_panel_inspected": True,
            "no_retained_old_regions": True,
            "photo_difference_score": 1.0 + metric_offset,
            "photo_luminance_mean": 120.0 + metric_offset,
            "photo_luminance_standard_deviation": 20.0 + metric_offset,
        }
    else:
        visual = {
            "map_fidelity_pass": state is ResultState.PASS,
            "orientation_pass": True,
            "seam_assessment_pass": True,
            "full_panel_inspected": True,
            "all_six_colors_present": True,
            "no_retained_old_regions": True,
        }
    assets = execution._registered_asset_identity(snapshot.plan)
    base: dict[str, Any] = {
        "schema_version": 1,
        "kind": runner.OPERATOR_OBSERVATION_KIND,
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "observed_at": TARGET_OBSERVED_AT if target else MAP_OBSERVED_AT,
        "reference_preview_sha256": snapshot.reference_preview["sha256"],
        "visual": visual,
        "electrical": {
            "meter_asset_sha256": fixture_sha256("n3-meter-v1"),
            "clock_asset_sha256": assets["timing_clock_asset_sha256"],
            "pre_voltage_v": 3.3,
            "pre_idle_current_a": 0.001,
            "post_voltage_v": 3.29,
            "post_idle_current_a": 0.001,
            "peak_current_a": 0.2,
            "constant_voltage_mode": True,
            "reviewed_limits_pass": True,
        },
        "thermal": {
            "pre_action_c": 24.0,
            "post_action_c": 25.0,
            "session_max_c": 25.5,
            "uncertainty_u95_c": 0.25,
            "sensor_asset_sha256": assets["temperature_sensor_asset_sha256"],
            "calibration_artifact_sha256": assets[
                "temperature_calibration_asset_sha256"
            ],
            "measurement_location_asset_sha256": assets[
                "temperature_location_asset_sha256"
            ],
            "measurement_evidence_sha256": fixture_sha256(
                f"n3-temperature:{snapshot.key}"
            ),
            "uncertainty_evidence_sha256": fixture_sha256("n3-temperature-u95-v1"),
        },
        "continuity": (
            {
                "controller_reboot_between_actions": False,
                "panel_power_cycle_between_actions": False,
                "j2_disconnect_between_actions": False,
                "other_visible_refresh_between_actions": False,
            }
            if target
            else None
        ),
        "camera": {
            "capture_performed": target,
            "file": None,
            "capture_file_sha256": None,
        },
    }
    if overrides:
        for key, value in overrides.items():
            if isinstance(value, Mapping) and isinstance(base.get(key), dict):
                base[key].update(deepcopy(dict(value)))
            else:
                base[key] = deepcopy(value)
    if target and base["camera"]["capture_performed"]:
        capture = root / f"{snapshot.key}.png"
        digest = hashlib.sha256(snapshot.key.encode("ascii")).digest()
        Image.new("RGB", (8, 8), color=tuple(digest[:3])).save(capture, format="PNG")
        payload = capture.read_bytes()
        base["camera"].update(
            {
                "file": str(capture),
                "capture_file_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    return base


def build_finalized_bundle(
    plan: Mapping[str, Any],
    action_key: str,
    *,
    prior_bundle: Optional[Mapping[str, Any]] = None,
    state: ResultState = ResultState.PASS,
    metric_offset: float = 0.0,
    overrides: Optional[Mapping[str, Any]] = None,
    _session_sink: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    frozen = execution.validate_n3_exact_plan(plan)
    snapshot = execution.load_n3_action_snapshot(frozen, action_key)
    target = snapshot.phase == "target"
    if target != (prior_bundle is not None):
        raise ValueError("N3 target requires prior_bundle; MAP forbids it")
    hardware = runner.REPO_ROOT / ".test-output" / "hardware"
    hardware.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=hardware) as temporary:
        root = Path(temporary)
        registry = root / "claims"
        prior_result: Optional[Path] = None
        if prior_bundle is not None:
            prior_result = _materialize_bundle(root, registry, prior_bundle)
        profile = _profile(snapshot.campaign, prior_completed=target)
        profile_path = _write_json(root / "profile.json", profile)
        destination = root / "result"
        if target:
            run_contract = runner._target_contract(snapshot)
            responses = target_responses(snapshot.frame, run_contract)
            completed = prior_bundle["evidence"]["protocol_evidence"][
                "completed_map_evidence"
            ]
            responses["/api/job"][0] = (200, json.dumps(completed["job_raw"]))
            responses["/api/diagnostic/report"][0] = (
                200,
                json.dumps(completed["diagnostic_raw"]),
            )
            scripted = ScriptedRequester(responses)
            clock = TargetTickClock()
            evaluated_at = TARGET_EVALUATED_AT
            runner_now = "2026-08-08T00:02:30Z"
        else:
            scripted = ScriptedRequester(map_responses())
            clock = MapTickClock()
            evaluated_at = EVALUATED_AT
            runner_now = "2026-08-08T00:00:30Z"
        plan_sha = execution.exact_plan_file_sha256(frozen)
        with (
            mock.patch.object(runner, "_require_deep_production_profile_path"),
            mock.patch.object(runner, "DEFAULT_CLAIM_REGISTRY", registry),
            mock.patch.object(runner, "http_request", scripted),
            mock.patch.object(runner, "_utc_now", return_value=runner_now),
        ):
            runner.run_n3_fixed_action_once(
                frozen,
                plan_sha,
                action_key,
                destination,
                "http://device",
                limit_profile_file=profile_path,
                evaluated_at=evaluated_at,
                authorization_confirmation=runner.required_authorization_confirmation(
                    frozen, action_key
                ),
                start_temperature_c=25,
                primer_result_file=prior_result,
                confirm_reviewed_panel_build_and_exact_plan=True,
                confirm_registered_measurement_assets_present=True,
                confirm_supervised_supply_cv_current_normal=True,
                confirm_physical_cutoff_available=True,
                confirm_single_visible_refresh=True,
                confirm_controller_fresh_boot=not target,
                confirm_map_fidelity_from_primer=target,
                confirm_esp32_not_restarted_since_primer=target,
                confirm_no_j2_disconnect_since_primer=target,
                confirm_no_panel_power_cycle_since_primer=target,
                confirm_no_other_visible_refresh_since_primer=target,
                sleeper=lambda _seconds: None,
                clock=clock,
            )
            observation = _operator_observation(
                snapshot,
                root=root,
                state=state,
                metric_offset=metric_offset,
                overrides=overrides,
            )
            observation_path = _write_json(root / "operator-observation.json", observation)
            finalized = runner.finalize_n3_observation(
                frozen,
                plan_sha,
                destination,
                observation_path,
                primer_result_file=prior_result,
            )
            bundle = runner._load_bundle_from_result_file(
                destination / runner.P0_RESULT_FILENAME
            )
            execution.validate_n3_finalized_action_bundle(
                frozen,
                bundle,
                expected_action_key=action_key,
                prior_bundle=prior_bundle,
            )
            if target:
                session_path = destination / runner.SESSION_OBSERVATION_FILENAME
                session_payload = session_path.read_bytes()
                session = json.loads(session_payload.decode("utf-8"))
                if canonical_json_bytes(session) != session_payload:
                    raise AssertionError("N3 session observation is not canonical")
                if finalized["session_observation_file_sha256"] != hashlib.sha256(
                    session_payload
                ).hexdigest():
                    raise AssertionError("N3 session observation hash changed")
                if _session_sink is not None:
                    _session_sink.update(
                        {
                            "session_observation": deepcopy(session),
                            "session_observation_file_sha256": hashlib.sha256(
                                session_payload
                            ).hexdigest(),
                        }
                    )
            return deepcopy(dict(bundle))


def build_finalized_session(
    plan: Mapping[str, Any],
    route_index: int,
    *,
    metric_offset: float = 0.0,
    map_overrides: Optional[Mapping[str, Any]] = None,
    target_overrides: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    route = plan["selected_routes"][route_index]
    map_bundle = build_finalized_bundle(
        plan, route["map_action_key"], overrides=map_overrides
    )
    target_bundle = build_finalized_bundle(
        plan,
        route["target_action_key"],
        prior_bundle=map_bundle,
        metric_offset=metric_offset,
        overrides=target_overrides,
    )
    return {"map_bundle": map_bundle, "target_bundle": target_bundle}


__all__ = [
    "build_finalized_bundle",
    "build_finalized_session",
    "fixture_sha256",
    "registered_assets",
]
