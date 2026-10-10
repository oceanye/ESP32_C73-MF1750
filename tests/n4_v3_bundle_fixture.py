"""Test-only builder for canonical N4 V3 finalized action bundles."""

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
from tools import g1_s1_n4_v3_execution_contract as execution
from tools import g1_s1_rc2g_n2_photo_campaign_once as n2_runner
from tools import g1_s1_rc2g_n4_v3_once as runner


EVALUATED_AT = "2026-08-08T00:00:15Z"
TARGET_EVALUATED_AT = "2026-08-08T00:02:00Z"
MAP_OBSERVED_AT = "2026-08-08T00:01:00Z"
TARGET_OBSERVED_AT = "2026-08-08T00:03:00Z"


def fixture_sha256(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


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
            "profile_id": "n4-v3-test-only-reviewed-profile",
            "profile_version": "1.0.0",
            "panel": dict(campaign["panel"]),
            "firmware": dict(campaign["firmware"]),
            "action_allowlist": allowlist,
            "limits": {
                "maximum_campaign_visible_refreshes": 8,
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
                "evidence_sha256": fixture_sha256("usage-evidence"),
            },
            "validity": {
                "valid_from": "2026-08-08T00:00:00Z",
                "expires_at": "2026-09-01T00:00:00Z",
            },
            "review": {
                "approved": True,
                "reviewer_id": "n4-v3-test-reviewer",
                "reviewed_at": "2026-08-07T23:00:00Z",
                "review_artifact_sha256": fixture_sha256("review-artifact"),
            },
        }
    )


def _materialize_bundle(
    root: Path,
    registry: Path,
    bundle: Mapping[str, Any],
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


def _merge(base: dict[str, Any], override: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    if not override:
        return base
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key].update(deepcopy(dict(value)))
        else:
            result[key] = deepcopy(value)
    return result


def _operator_observation(
    snapshot: execution.N4V3ActionSnapshot,
    *,
    root: Path,
    state: ResultState,
    score_offset: float,
    electrical_offset: float,
    overrides: Optional[Mapping[str, Any]],
) -> dict[str, Any]:
    target = snapshot.phase == "target"
    visual: dict[str, Any]
    if target:
        visual = {
            "roi_definition_sha256": fixture_sha256("fixed-roi-v1"),
            "target_fidelity_pass": state is ResultState.PASS,
            "orientation_pass": True,
            "seam_assessment_pass": True,
            "full_panel_inspected": True,
            "no_retained_old_regions": True,
            "fidelity_score": 0.8 + score_offset,
            "ghosting_score": 0.1 + score_offset,
            "artifact_severity_score": 0.2 + score_offset,
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
    electrical = {
        "meter_asset_sha256": fixture_sha256("meter-v1"),
        "clock_asset_sha256": fixture_sha256("clock-v1"),
        "pre_voltage_v": 3.3,
        "pre_idle_current_a": 0.001,
        "post_voltage_v": 3.29 - electrical_offset,
        "post_idle_current_a": 0.001,
        "peak_current_a": 0.20 + electrical_offset,
        "constant_voltage_mode": True,
        "reviewed_limits_pass": True,
    }
    thermal = {
        "pre_action_c": 24.0 + electrical_offset,
        "post_action_c": 25.0 + electrical_offset,
        "session_max_c": 25.5 + electrical_offset,
        "uncertainty_u95_c": 0.25,
        "sensor_asset_sha256": fixture_sha256("temperature-sensor-v1"),
        "calibration_artifact_sha256": fixture_sha256("temperature-calibration-v1"),
        "measurement_evidence_sha256": fixture_sha256(
            f"temperature:{snapshot.key}"
        ),
        "uncertainty_evidence_sha256": fixture_sha256("temperature-u95-v1"),
    }
    continuity = (
        {
            "controller_reboot_between_actions": False,
            "panel_power_cycle_between_actions": False,
            "j2_disconnect_between_actions": False,
            "other_visible_refresh_between_actions": False,
        }
        if target
        else None
    )
    camera = {
        "observation_kind": "standardized-manual",
        "observer_or_camera_asset_sha256": fixture_sha256("observer-v1"),
        "file": None,
        "capture_file_sha256": None,
        "fixed_exposure_profile_sha256": None,
    }
    merged = _merge(
        {
            "schema_version": 1,
            "kind": runner.OPERATOR_OBSERVATION_KIND,
            "action_key": snapshot.key,
            "action_identity_sha256": snapshot.action["action_identity_sha256"],
            "observed_at": TARGET_OBSERVED_AT if target else MAP_OBSERVED_AT,
            "reference_preview_sha256": snapshot.reference_preview["sha256"],
            "visual": visual,
            "electrical": electrical,
            "thermal": thermal,
            "continuity": continuity,
            "camera": camera,
        },
        overrides,
    )
    if merged["camera"].get("observation_kind") == "fixed-camera":
        capture = root / f"{snapshot.key}.png"
        digest = hashlib.sha256(snapshot.key.encode("ascii")).digest()
        Image.new("RGB", (8, 8), color=tuple(digest[:3])).save(capture, format="PNG")
        payload = capture.read_bytes()
        merged["camera"].update(
            {
                "file": str(capture),
                "capture_file_sha256": hashlib.sha256(payload).hexdigest(),
                "fixed_exposure_profile_sha256": merged["camera"].get(
                    "fixed_exposure_profile_sha256"
                )
                or fixture_sha256("fixed-exposure-v1"),
            }
        )
    return merged


def build_finalized_bundle(
    action_key: str,
    *,
    contract: Optional[Mapping[str, Any]] = None,
    prior_bundle: Optional[Mapping[str, Any]] = None,
    state: ResultState = ResultState.PASS,
    score_offset: float = 0.0,
    electrical_offset: float = 0.0,
    overrides: Optional[Mapping[str, Any]] = None,
    _cell_sink: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build one valid deep chain through the production runner using mock HTTP."""

    frozen = (
        execution.compile_n4_v3_execution_contract()
        if contract is None
        else execution.validate_n4_v3_execution_contract(contract)
    )
    snapshot = execution.load_n4_v3_action_snapshot(action_key)
    target = snapshot.phase == "target"
    if target != (prior_bundle is not None):
        raise ValueError("target requires prior_bundle; MAP forbids it")
    hardware = runner.REPO_ROOT / ".test-output" / "hardware"
    hardware.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=hardware) as temporary:
        root = Path(temporary)
        registry = root / "claims"
        prior_result: Optional[Path] = None
        if prior_bundle is not None:
            prior_result = _materialize_bundle(root, registry, prior_bundle)
        profile = _profile(frozen["p0_campaign"], prior_completed=target)
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
        with (
            mock.patch.object(runner, "_require_deep_production_profile_path"),
            mock.patch.object(n2_runner, "DEFAULT_CLAIM_REGISTRY", registry),
            mock.patch.object(runner, "http_request", scripted),
            mock.patch.object(
                runner, "_utc_now", return_value=runner_now
            ),
        ):
            runner.run_n4_v3_fixed_action_once(
                action_key,
                destination,
                "http://device",
                limit_profile_file=profile_path,
                evaluated_at=evaluated_at,
                authorization_confirmation=runner.required_authorization_confirmation(
                    action_key
                ),
                start_temperature_c=25,
                primer_result_file=prior_result,
                confirm_reviewed_panel_and_build=True,
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
                score_offset=score_offset,
                electrical_offset=electrical_offset,
                overrides=overrides,
            )
            observation_path = _write_json(root / "operator-observation.json", observation)
            finalized = runner.finalize_n4_v3_observation(
                destination,
                observation_path,
                primer_result_file=prior_result,
            )
            bundle = runner._load_bundle_from_result_file(
                destination / runner.P0_RESULT_FILENAME
            )
            execution.validate_n4_v3_finalized_action_bundle(
                frozen,
                bundle,
                expected_action_key=action_key,
                prior_bundle=prior_bundle,
            )
            if target:
                from tools import g1_s1_n4_v3_analyzer as analyzer

                cell_path = destination / runner.CELL_OBSERVATION_FILENAME
                cell_payload = cell_path.read_bytes()
                cell_observation = json.loads(cell_payload.decode("utf-8"))
                if canonical_json_bytes(cell_observation) != cell_payload:
                    raise AssertionError("cell observation is not canonical JSON")
                analysis_contract = analyzer.compile_n4_v3_analysis_contract()
                analyzer.validate_n4_v3_cell_observation(
                    cell_observation, analysis_contract
                )
                if finalized["cell_observation_file_sha256"] != hashlib.sha256(
                    cell_payload
                ).hexdigest():
                    raise AssertionError("cell observation file hash changed")
                if _cell_sink is not None:
                    _cell_sink.update(
                        {
                            "cell_observation": deepcopy(cell_observation),
                            "cell_observation_file_sha256": hashlib.sha256(
                                cell_payload
                            ).hexdigest(),
                        }
                    )
            return deepcopy(dict(bundle))


def build_finalized_cell(
    cell_id: str,
    *,
    contract: Optional[Mapping[str, Any]] = None,
    score_offset: float = 0.0,
    electrical_offset: float = 0.0,
    map_overrides: Optional[Mapping[str, Any]] = None,
    target_overrides: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Build a MAP bundle, target bundle, and persisted cell observation."""

    map_bundle = build_finalized_bundle(
        f"{cell_id}-map-primer",
        contract=contract,
        electrical_offset=electrical_offset,
        overrides=map_overrides,
    )
    cell: dict[str, Any] = {}
    target_bundle = build_finalized_bundle(
        f"{cell_id}-target",
        contract=contract,
        prior_bundle=map_bundle,
        score_offset=score_offset,
        electrical_offset=electrical_offset,
        overrides=target_overrides,
        _cell_sink=cell,
    )
    return {
        "map_bundle": map_bundle,
        "target_bundle": target_bundle,
        **cell,
    }


__all__ = ["build_finalized_bundle", "build_finalized_cell", "fixture_sha256"]
