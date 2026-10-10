from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping, Optional
from unittest import mock

from host.visible_refresh_campaign import canonical_json_bytes
from host.visible_refresh_campaign import production_profile as production
from tests.test_frame_tool import ScriptedRequester
from tests.test_g1_s1_rc2g_map_baseline_once import (
    TickClock as MapTickClock,
    _responses as map_responses,
)
from tests.test_g1_s1_rc2g_quality_refresh_once import (
    TickClock as TargetTickClock,
    _responses as target_responses,
)
from tools import g1_s1_n2_physical_campaign as physical
from tools import g1_s1_rc2g_n2_photo_campaign as frozen
from tools import g1_s1_rc2g_n2_photo_campaign_once as legacy
from tools import g1_s1_rc2g_n2_physical_once as runner


MAP_EVALUATED_AT = "2026-08-08T00:00:30Z"
TARGET_EVALUATED_AT = "2026-08-08T00:04:00Z"
PRIMER_OBSERVED_AT = "2026-08-08T00:01:00Z"
TARGET_OBSERVED_AT = "2026-08-08T00:05:00Z"
PROCESS_SCHEDULE_SECONDS = 150

PANEL = {
    "model": "MF1750-C73",
    "serial": "MF1750-LAB-PANEL-0001",
    "board_id": "ESP32-C73",
    "pcb_revision": "rev-a1",
}
BINDING_REVIEW_BYTES = b"N2P physical runner test binding review v1\n"


def camera_none() -> dict[str, object]:
    return {
        "capture_performed": False,
        "file": None,
        "sha256": None,
        "camera_id": None,
        "tripod_position_id": None,
        "lighting_setup_id": None,
        "exposure_mode": None,
        "white_balance_mode": None,
        "focus_mode": None,
        "image_processing": None,
        "full_panel_uncropped": None,
    }


def electrical_pass() -> dict[str, bool]:
    return {
        "supply_3v3_normal": True,
        "cv_mode_normal": True,
        "current_normal": True,
        "temperature_normal": True,
        "no_odor_sound_hotspot_damage_or_voltage_droop": True,
        "esp32_did_not_restart_during_action": True,
        "physical_cutoff_available": True,
        "visual_quality_scored_independently_from_electrical": True,
    }


def observation(
    snapshot: legacy._ActionSnapshot,
    *,
    target: bool,
    camera: Optional[Mapping[str, object]] = None,
) -> dict[str, object]:
    visual: dict[str, object]
    if target:
        visual = {
            "detail": 4,
            "tone": 4,
            "gradients": 4,
            "texture": 4,
            "artifacts": 4,
            "source_fidelity": 4,
            "screen_geometry_matches_reference": True,
            "no_retained_old_regions": True,
        }
    else:
        visual = {
            "screen_matches_reference": True,
            "orientation_correct": True,
            "labels_legible": True,
            "center_seam_correct": True,
            "all_six_colors_present": True,
            "no_retained_old_regions": True,
        }
    return {
        "schema_version": 1,
        "kind": runner.OBSERVATION_KIND,
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "observed_at": TARGET_OBSERVED_AT if target else PRIMER_OBSERVED_AT,
        "observer_id": "physical-runner-test-operator",
        "full_panel_inspected": True,
        "reference_preview_sha256": snapshot.reference_preview["sha256"],
        "viewing_distance_cm": 60,
        "stable_lighting": True,
        "visual": visual,
        "electrical": electrical_pass(),
        "post_refresh_temperature_c": 26.0,
        "camera": dict(camera) if camera is not None else camera_none(),
    }


class PhysicalOnceFixture:
    """Offline physical runner fixture reusable by analyzer tests."""

    def __init__(
        self,
        root: Path,
        frozen_manifest: Mapping[str, Any],
        *,
        authority_schedule_seconds: int = PROCESS_SCHEDULE_SECONDS,
        use_process_policy: bool = False,
    ) -> None:
        self.root = root
        self.frozen_manifest = deepcopy(frozen_manifest)
        self.authority_schedule_seconds = authority_schedule_seconds
        self.use_process_policy = use_process_policy
        self.registry = root / "claims"
        self.source_file = self.write_json("frozen-source.json", self.frozen_manifest)
        self.panel_file = self.write_json("physical-panel.json", PANEL)
        self.binding_review_file = root / "panel-binding-review.bin"
        self.binding_review_file.write_bytes(BINDING_REVIEW_BYTES)
        self.bundle_dir = root / "physical-bundle"
        self.reviewer_key_file = root / "trusted-reviewer.key"
        self.reviewer_key_file.write_bytes(bytes(range(32)))
        physical.publish_physical_bundle(
            self.source_file,
            self.panel_file,
            self.binding_review_file,
            self.bundle_dir,
            minimum_interval_seconds=PROCESS_SCHEDULE_SECONDS,
            planned_cooldown_seconds=PROCESS_SCHEDULE_SECONDS,
        )
        self.operator = json.loads(
            (self.bundle_dir / physical.OPERATOR_MANIFEST_FILENAME).read_text(
                encoding="utf-8"
            )
        )
        self._production: dict[str, dict[str, Any]] = {}

    def write_json(self, name: str, value: object) -> Path:
        path = self.root / name
        path.write_bytes(canonical_json_bytes(value))
        return path

    def action(self, action_key: str) -> Mapping[str, Any]:
        action_sha = self.operator["fixed_actions"][action_key]
        return next(
            action
            for action in self.operator["physical_campaign_contract"]["actions"]
            if action["action_identity_sha256"] == action_sha
        )

    def production_inputs(self, phase: str) -> dict[str, Any]:
        if phase in self._production:
            return dict(self._production[phase])
        if phase not in {"map-primer", "target"}:
            raise ValueError("phase must be map-primer or target")
        target = phase == "target"
        campaign = self.operator["physical_campaign_contract"]
        prefix = "target" if target else "map"
        snapshot_at = "2026-08-08T00:02:00Z" if target else "2026-08-08T00:00:00Z"
        reviewed_at = "2026-08-08T00:02:10Z" if target else "2026-08-08T00:00:05Z"
        valid_from = "2026-08-08T00:02:20Z" if target else "2026-08-08T00:00:10Z"
        evaluated_at = TARGET_EVALUATED_AT if target else MAP_EVALUATED_AT
        limits = {
            "maximum_campaign_visible_refreshes": 8,
            "maximum_session_visible_refreshes": 2,
            "maximum_consecutive_visible_refreshes": 2,
            "minimum_interval_seconds": self.authority_schedule_seconds,
            "minimum_cooldown_seconds": self.authority_schedule_seconds,
            "minimum_start_temperature_c": 0 if self.use_process_policy else 10,
            "maximum_start_temperature_c": 50 if self.use_process_policy else 40,
            "maximum_post_refresh_temperature_c": 50 if self.use_process_policy else 45,
        }
        validity = {
            "valid_from": valid_from,
            "expires_at": "2026-09-01T00:00:00Z",
        }
        if self.use_process_policy:
            provenance = {
                field: {
                    "classification": (
                        production.EXACT_SUPPLIER_DOCUMENT_PROVENANCE
                        if field
                        in {
                            "minimum_start_temperature_c",
                            "maximum_start_temperature_c",
                            "maximum_post_refresh_temperature_c",
                        }
                        else production.OPERATOR_SELECTED_PROCESS_GATE_PROVENANCE
                    ),
                    "source_document_sha256": (
                        production.MF1750_A1_SOURCE_DOCUMENT_SHA256
                    ),
                }
                for field in production._LIMIT_FIELDS
            }
            supplier = {
                "schema_version": 1,
                "kind": production.SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND,
                "not_a_supplier_rating": True,
                "supervised_only": True,
                "automatic_execution": False,
                "automatic_retry": False,
                "automatic_recovery": False,
                "issuer": "physical-runner-test-process-owner",
                "policy_id": f"n2p-{prefix}-process-policy-2026-08-08",
                "issued_at": "2026-08-07T20:00:00Z",
                "panel_model": PANEL["model"],
                "maximum_usage_snapshot_age_seconds": 7200,
                "limits": limits,
                "validity": validity,
                "field_provenance": provenance,
            }
        else:
            supplier = {
                "schema_version": 1,
                "kind": production.SUPPLIER_LIMITS_KIND,
                "supplier_id": "mf1750-physical-runner-test-supplier",
                "document_id": f"n2p-{prefix}-limits-2026-08-08",
                "issued_at": "2026-08-07T20:00:00Z",
                "panel_model": PANEL["model"],
                "maximum_usage_snapshot_age_seconds": 7200,
                "limits": limits,
                "validity": validity,
            }
        usage = {
            "schema_version": 1,
            "kind": production.USAGE_EVIDENCE_KIND,
            "evidence_id": f"n2p-{prefix}-usage-2026-08-08",
            "campaign_canonical_sha256": campaign["integrity"]["canonical_sha256"],
            "panel": campaign["panel"],
            "firmware": campaign["firmware"],
            "usage": {
                "cumulative_visible_refresh_count": 1 if target else 0,
                "session_visible_refresh_count": 1 if target else 0,
                "consecutive_visible_refresh_count": 1 if target else 0,
                "last_visible_refresh_completed_at": (
                    PRIMER_OBSERVED_AT if target else None
                ),
                "snapshot_at": snapshot_at,
            },
        }
        supplier_file = self.write_json(f"{prefix}-supplier.json", supplier)
        usage_file = self.write_json(f"{prefix}-usage.json", usage)
        campaign_file = self.bundle_dir / physical.PHYSICAL_CAMPAIGN_FILENAME
        inputs = {
            "campaign_file": campaign_file,
            "firmware_binary_file": frozen.FIRMWARE_BINARY,
            "supplier_limits_file": supplier_file,
            "usage_evidence_file": usage_file,
        }
        draft = production.compile_production_draft_from_files(
            **inputs,
            profile_id=f"n2p-{prefix}-physical-production-profile",
            profile_version="1.0.0",
        )
        draft_file = self.write_json(f"{prefix}-profile-draft.json", draft)
        bundle = production.create_production_approval(
            draft_profile_file=draft_file,
            **inputs,
            reviewer_id="trusted-n2p-physical-reviewer",
            reviewed_at=reviewed_at,
            reviewer_key_file=self.reviewer_key_file,
        )
        review_file = self.root / f"{prefix}-profile-review.json"
        profile_file = self.root / f"{prefix}-profile.json"
        production.publish_approval_bundle(
            bundle,
            review_artifact_output=review_file,
            profile_output=profile_file,
        )
        result = {
            "bundle_dir": self.bundle_dir,
            "source_manifest_file": self.source_file,
            "panel_file": self.panel_file,
            "binding_review_artifact_file": self.binding_review_file,
            "profile_file": profile_file,
            "firmware_binary_file": frozen.FIRMWARE_BINARY,
            "supplier_limits_file": supplier_file,
            "usage_evidence_file": usage_file,
            "profile_review_artifact_file": review_file,
            "reviewer_key_file": self.reviewer_key_file,
            "evaluated_at": evaluated_at,
        }
        self._production[phase] = result
        return dict(result)

    def context(self, action_key: str) -> runner._Context:
        phase = str(self.action(action_key)["identity"]["phase"])
        return runner._load_live_context(
            action_key, **self.production_inputs(phase)
        )

    def run_and_finalize(
        self,
        action_key: str,
        result_name: str,
        *,
        primer_result_dir: Optional[Path] = None,
        camera: Optional[Mapping[str, object]] = None,
        evaluated_at: Optional[str] = None,
    ) -> tuple[Path, ScriptedRequester]:
        production_inputs = self.production_inputs(
            str(self.action(action_key)["identity"]["phase"])
        )
        if evaluated_at is not None:
            production_inputs["evaluated_at"] = evaluated_at
        context = runner._load_live_context(action_key, **production_inputs)
        phase = context.legacy_snapshot.phase
        authorization = runner.required_action_authorization(
            context.action["action_identity_sha256"]
        )
        panel_confirmation = runner.required_panel_build_confirmation(
            str(context.campaign["panel"]["serial"]),
            str(context.campaign["firmware"]["build_tag"]),
            str(
                context.operator["physical_binding"]["integrity"][
                    "canonical_sha256"
                ]
            ),
        )
        profile_confirmation = runner._profile_confirmation(context)
        if phase == "map-primer":
            scripted = ScriptedRequester(map_responses())
            clock = MapTickClock()
        else:
            if primer_result_dir is None:
                raise ValueError("target fixture requires primer_result_dir")
            contract = legacy._target_contract(
                context.legacy_snapshot,
                required_authorization_confirmation_override=authorization,
            )
            responses = target_responses(context.legacy_snapshot.frame, contract)
            primer_evidence = json.loads(
                (primer_result_dir / runner.EVIDENCE_FILENAME).read_text(
                    encoding="utf-8"
                )
            )
            completed = primer_evidence["protocol_evidence"]["completed_map_evidence"]
            responses["/api/job"][0] = (200, json.dumps(completed["job_raw"]))
            responses["/api/diagnostic/report"][0] = (
                200,
                json.dumps(completed["diagnostic_raw"]),
            )
            scripted = ScriptedRequester(responses)
            clock = TargetTickClock()
        destination = self.root / result_name
        claim_file = self.registry / f"{context.action['action_identity_sha256']}.json"

        def claim_before_network(*args: Any, **kwargs: Any) -> tuple[int, str]:
            if not claim_file.is_file():
                raise AssertionError("workspace-global claim was not created before network")
            return scripted(*args, **kwargs)

        run_kwargs = {
            **production_inputs,
            "authorization_confirmation": authorization,
            "panel_build_confirmation": panel_confirmation,
            "profile_confirmation": profile_confirmation,
            "start_temperature_c": 25,
            "primer_result_dir": primer_result_dir,
            "confirm_supervised_supply_cv_current_normal": True,
            "confirm_physical_cutoff_available": True,
            "confirm_single_visible_refresh": True,
            "confirm_controller_fresh_boot": phase == "map-primer",
            "confirm_map_fidelity_from_primer": phase == "target",
            "confirm_esp32_not_restarted_since_primer": phase == "target",
            "confirm_no_j2_disconnect_since_primer": phase == "target",
            "confirm_no_panel_power_cycle_since_primer": phase == "target",
            "confirm_no_other_visible_refresh_since_primer": phase == "target",
            "sleeper": lambda _seconds: None,
            "clock": clock,
        }
        with (
            mock.patch.object(runner, "DEFAULT_CLAIM_REGISTRY", self.registry),
            mock.patch.object(runner, "_utc_now", return_value=str(run_kwargs["evaluated_at"])),
            mock.patch.object(legacy, "http_request", side_effect=claim_before_network),
        ):
            runner.run_physical_action_once(
                action_key,
                destination,
                "http://device",
                **run_kwargs,
            )
        observation_file = self.write_json(
            f"{result_name}-observation-input.json",
            observation(
                context.legacy_snapshot,
                target=phase == "target",
                camera=camera,
            ),
        )
        with (
            mock.patch.object(runner, "DEFAULT_CLAIM_REGISTRY", self.registry),
            mock.patch.object(legacy, "_utc_now", return_value="2026-08-08T00:05:00Z"),
        ):
            finalized = runner.finalize_physical_observation(
                destination,
                observation_file,
                reviewer_key_file=self.reviewer_key_file,
            )
        if finalized["state"] != "PASS":
            raise AssertionError("fixture action did not finalize PASS")
        return destination, scripted
