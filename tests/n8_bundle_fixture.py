"""Test-only production-path builder for deep N8 finalized bundles."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping, Optional
from unittest import mock

from PIL import Image

from host.visible_refresh_campaign import LIMIT_PROFILE_KIND, ResultState, canonical_json_bytes, seal_limit_profile
from tests.test_frame_tool import ScriptedRequester
from tests.test_g1_s1_rc2g_map_baseline_once import TickClock as MapTickClock, _responses as map_responses
from tests.test_g1_s1_rc2g_quality_refresh_once import TickClock as TargetTickClock, _responses as target_responses
from tools import g1_s1_n8_carryover_campaign as campaign
from tools import g1_s1_n8_execution_contract as execution
from tools import g1_s1_rc2g_n2_photo_campaign as n2
from tools import g1_s1_rc2g_n2_photo_campaign_once as n2_runner
from tools import g1_s1_rc2g_n8_once as runner


EVALUATED_AT = "2026-08-08T00:00:00Z"
OBSERVED_AT = "2026-08-08T00:01:00Z"
RUNNER_NOW = "2026-08-08T00:00:30Z"


def evaluated_at(snapshot: execution.N8ActionSnapshot) -> str:
    return f"2026-08-08T00:{2 * (snapshot.ordinal - 1):02d}:00Z"


def observed_at(snapshot: execution.N8ActionSnapshot) -> str:
    return f"2026-08-08T00:{2 * snapshot.ordinal - 1:02d}:00Z"


def runner_now(snapshot: execution.N8ActionSnapshot) -> str:
    return f"2026-08-08T00:{2 * (snapshot.ordinal - 1):02d}:30Z"


def fixture_sha256(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


PANEL = {
    "model": "MF1750-C73",
    "serial": "TEST-ONLY-N8-PANEL-001",
    "board_id": "ESP32-C73",
    "pcb_revision": "rev-a1",
}


def measurements() -> dict[str, Any]:
    return campaign.build_measurement_registry(
        external_temperature_sensor_sha256=fixture_sha256("n8-temperature-sensor"),
        external_temperature_calibration_sha256=fixture_sha256("n8-temperature-calibration"),
        external_temperature_location_sha256=fixture_sha256("n8-temperature-location"),
        external_temperature_u95_c=0.25,
        camera_body_sha256=fixture_sha256("n8-camera-body"),
        camera_lens_sha256=fixture_sha256("n8-camera-lens"),
        camera_mount_sha256=fixture_sha256("n8-camera-mount"),
        fixed_exposure_profile_sha256=fixture_sha256("n8-camera-exposure"),
        camera_crop_sha256=fixture_sha256("n8-camera-crop"),
        illumination_sha256=fixture_sha256("n8-illumination"),
        electrical_meter_sha256=fixture_sha256("n8-meter"),
        timing_clock_sha256=fixture_sha256("n8-clock"),
    )


def bindings() -> dict[str, Any]:
    return campaign.build_binding_registry(
        supplier_limit_document_sha256=fixture_sha256("n8-supplier-limits"),
        panel_instance_binding_sha256=fixture_sha256("n8-panel-binding"),
        firmware_build_binding_sha256=fixture_sha256("n8-firmware-binding"),
    )


def bins() -> dict[str, Any]:
    return campaign.build_temperature_bin_plan(
        supplier_definition_sha256=fixture_sha256("n8-temperature-bins"),
        low_minimum_c=0,
        low_maximum_c=15,
        nominal_minimum_c=15,
        nominal_maximum_c=30,
        high_minimum_c=30,
        high_maximum_c=45,
    )


def profile(
    draft: Mapping[str, Any],
    *,
    cumulative_count: int = 0,
    snapshot_at: str = "2026-08-08T00:00:00Z",
    last_visible_refresh_completed_at: Optional[str] = None,
) -> dict[str, Any]:
    allowlist = []
    for action in draft["p0_campaign"]["actions"]:
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
            "profile_id": "n8-test-only-reviewed-profile",
            "profile_version": "1.0.0",
            "panel": PANEL,
            "firmware": n2.FIRMWARE_CONTRACT,
            "action_allowlist": allowlist,
            "limits": {
                "maximum_campaign_visible_refreshes": 100,
                "maximum_session_visible_refreshes": 10,
                "maximum_consecutive_visible_refreshes": 10,
                "minimum_interval_seconds": 0,
                "minimum_cooldown_seconds": 0,
                "minimum_start_temperature_c": 0,
                "maximum_start_temperature_c": 45,
                "maximum_post_refresh_temperature_c": 50,
            },
            "usage": {
                "cumulative_visible_refresh_count": cumulative_count,
                "session_visible_refresh_count": cumulative_count,
                "consecutive_visible_refresh_count": cumulative_count,
                "last_visible_refresh_completed_at": last_visible_refresh_completed_at,
                "snapshot_at": snapshot_at,
                "evidence_sha256": fixture_sha256("n8-usage"),
            },
            "validity": {
                "valid_from": "2026-08-07T00:00:00Z",
                "expires_at": "2026-09-01T00:00:00Z",
            },
            "review": {
                "approved": True,
                "reviewer_id": "n8-test-reviewer",
                "reviewed_at": "2026-08-07T00:00:00Z",
                "review_artifact_sha256": fixture_sha256("n8-supplier-limits"),
            },
        }
    )


def ready_manifest(
    *,
    cumulative_count: int = 0,
    snapshot_at: str = "2026-08-08T00:00:00Z",
    last_visible_refresh_completed_at: Optional[str] = None,
) -> dict[str, Any]:
    draft = campaign.compile_n8_manifest(
        panel=PANEL,
        measurement_registry=measurements(),
        binding_registry=bindings(),
        temperature_bin_plan=bins(),
    )
    return campaign.compile_n8_manifest(
        panel=PANEL,
        measurement_registry=measurements(),
        binding_registry=bindings(),
        temperature_bin_plan=bins(),
        limit_profile=profile(
            draft,
            cumulative_count=cumulative_count,
            snapshot_at=snapshot_at,
            last_visible_refresh_completed_at=last_visible_refresh_completed_at,
        ),
    )


def _write_json(path: Path, value: Mapping[str, Any]) -> Path:
    path.write_bytes(canonical_json_bytes(value))
    return path


def _temperature_for(snapshot: execution.N8ActionSnapshot) -> float:
    return {
        "supplier-low": 10.0,
        "supplier-nominal": 22.0,
        "supplier-high": 35.0,
        None: 24.0,
    }[snapshot.temperature_bin_id]


def confirmations(snapshot: execution.N8ActionSnapshot) -> dict[str, bool]:
    return {key: True for key in runner._confirmation_fields(snapshot)}


def operator_observation(
    snapshot: execution.N8ActionSnapshot,
    *,
    root: Path,
    runtime: Mapping[str, Any],
    state: ResultState = ResultState.PASS,
    score_offset: float = 0.0,
    overrides: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    capture = root / f"{snapshot.key}.png"
    color = tuple(hashlib.sha256(snapshot.key.encode("ascii")).digest()[:3])
    Image.new("RGB", (8, 8), color=color).save(capture, format="PNG")
    payload = capture.read_bytes()
    external = runtime["measurement_registry"]["external_temperature"]
    pre = _temperature_for(snapshot)
    value: dict[str, Any] = {
        "schema_version": 1,
        "kind": runner.OPERATOR_OBSERVATION_KIND,
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "observed_at": observed_at(snapshot),
        "reference_preview_sha256": snapshot.reference_preview["sha256"],
        "visual": {
            "fidelity_pass": state is ResultState.PASS,
            "orientation_pass": True,
            "seam_assessment_pass": True,
            "full_panel_inspected": True,
            "all_six_colors_present": True,
            "no_retained_old_regions": True,
            "ghosting_score": 0.1 + score_offset,
            "artifact_severity_score": 0.2 + score_offset,
        },
        "electrical": {
            "meter_asset_sha256": runtime["measurement_registry"]["electrical"]["meter_asset_sha256"],
            "clock_asset_sha256": runtime["measurement_registry"]["timing"]["clock_asset_sha256"],
            "pre_voltage_v": 3.3,
            "pre_idle_current_a": 0.001,
            "post_voltage_v": 3.3,
            "post_idle_current_a": 0.001,
            "peak_current_a": 0.3,
            "constant_voltage_mode": True,
            "reviewed_limits_pass": True,
        },
        "external_temperature": {
            "pre_action_c": pre,
            "post_action_c": pre + 1,
            "session_max_c": pre + 2,
            "uncertainty_u95_c": external["uncertainty_u95_c"],
            "sensor_asset_sha256": external["sensor_asset_sha256"],
            "calibration_artifact_sha256": external["calibration_artifact_sha256"],
            "measurement_location_sha256": external["measurement_location_sha256"],
            "measurement_evidence_sha256": fixture_sha256(f"n8-temperature:{snapshot.key}"),
            "uncertainty_evidence_sha256": fixture_sha256("n8-temperature-u95"),
        },
        "continuity": None if snapshot.ordinal == 1 else {
            "controller_reboot_between_actions": False,
            "panel_power_cycle_between_actions": False,
            "j2_disconnect_between_actions": False,
            "other_visible_refresh_between_actions": False,
        },
        "camera": {
            "file": str(capture),
            "capture_file_sha256": hashlib.sha256(payload).hexdigest(),
            "capture_evidence_sha256": fixture_sha256(f"n8-capture:{snapshot.key}"),
        },
    }
    if overrides:
        value = deepcopy(value)
        for key, item in overrides.items():
            if isinstance(item, Mapping) and isinstance(value.get(key), dict):
                value[key].update(deepcopy(dict(item)))
            else:
                value[key] = deepcopy(item)
    return value


def build_finalized_bundle(
    action_key: str,
    *,
    runtime: Optional[Mapping[str, Any]] = None,
    prior_bundle: Optional[Mapping[str, Any]] = None,
    state: ResultState = ResultState.PASS,
    score_offset: float = 0.0,
    overrides: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    selected_runtime = ready_manifest() if runtime is None else runtime
    snapshot = execution.load_n8_action_snapshot(action_key)
    if (snapshot.ordinal > 1) != (prior_bundle is not None):
        raise ValueError("dependent action requires prior bundle; root forbids it")
    if prior_bundle is not None:
        prior_completed_at = prior_bundle["result"]["completed_at"]
        selected_runtime = ready_manifest(
            cumulative_count=snapshot.ordinal - 1,
            snapshot_at=prior_completed_at,
            last_visible_refresh_completed_at=prior_completed_at,
        )
    action_evaluated_at = evaluated_at(snapshot)
    hardware = runner.REPO_ROOT / ".test-output" / "hardware"
    hardware.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=hardware) as temporary:
        root = Path(temporary)
        registry = root / "claims"
        registry.mkdir()
        manifest_path = _write_json(root / "runtime.json", selected_runtime)
        prior_path: Optional[Path] = None
        if prior_bundle is not None:
            prior_path = _write_json(root / "prior.json", prior_bundle)
            completed = prior_bundle["evidence"]["protocol_evidence"]["completed_action"]
            run_contract = execution.build_n8_protocol_contract(
                snapshot,
                prior_job_id=completed["job_id"],
                prior_operation_id=completed["operation_id"],
            )
            responses = target_responses(snapshot.frame, run_contract)
            responses["/api/job"][0] = (200, json.dumps(completed["job_raw"]))
            responses["/api/diagnostic/report"][0] = (200, json.dumps(completed["diagnostic_raw"]))
            requester = ScriptedRequester(responses)
            clock = TargetTickClock()
        else:
            requester = ScriptedRequester(map_responses())
            clock = MapTickClock()
        destination = root / "result"
        with (
            mock.patch.object(n2_runner, "DEFAULT_CLAIM_REGISTRY", registry),
            mock.patch.object(runner, "http_request", requester),
            mock.patch.object(runner, "_utc_now", return_value=runner_now(snapshot)),
        ):
            runner._run_n8_fixed_action_once_legacy_test_only(
                action_key,
                destination,
                "http://device",
                runtime_manifest_file=manifest_path,
                evaluated_at=action_evaluated_at,
                authorization_confirmation=runner.required_authorization_confirmation(action_key),
                start_external_temperature_c=_temperature_for(snapshot),
                prior_bundle_file=prior_path,
                confirmations=confirmations(snapshot),
                sleeper=lambda _seconds: None,
                clock=clock,
            )
            observation = operator_observation(
                snapshot, root=root, runtime=selected_runtime, state=state,
                score_offset=score_offset, overrides=overrides,
            )
            observation_path = _write_json(root / "observation-input.json", observation)
            finalized = runner.finalize_n8_observation(destination, observation_path)
        return finalized["bundle"]


def build_sequence(
    sequence_id: str,
    *,
    runtime: Optional[Mapping[str, Any]] = None,
    states: Optional[Mapping[int, ResultState]] = None,
) -> list[dict[str, Any]]:
    selected_runtime = ready_manifest() if runtime is None else runtime
    sequence = next(item for item in selected_runtime["sequences"] if item["sequence_id"] == sequence_id)
    bundles: list[dict[str, Any]] = []
    prior: Optional[Mapping[str, Any]] = None
    for action in sequence["actions"]:
        if prior is not None and prior["result"]["state"] != ResultState.PASS.value:
            break
        key = next(key for key, sha in execution.FIXED_ACTION_SHA256S.items() if sha == action["action_identity_sha256"])
        bundle = build_finalized_bundle(
            key, runtime=selected_runtime, prior_bundle=prior,
            state=(states or {}).get(action["ordinal"], ResultState.PASS),
            score_offset=action["ordinal"] / 100,
        )
        bundles.append(bundle)
        prior = bundle
    return bundles


@lru_cache(maxsize=1)
def build_all_pass() -> tuple[dict[str, Any], ...]:
    selected_runtime = ready_manifest()
    bundles: list[dict[str, Any]] = []
    for sequence_id in campaign.N8_SEQUENCE_IDS:
        bundles.extend(build_sequence(sequence_id, runtime=selected_runtime))
    return tuple(bundles)
