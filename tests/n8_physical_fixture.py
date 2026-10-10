"""Offline-only full-chain fixture for physical N8 runner/analyzer tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Optional
from unittest import mock

from host.visible_refresh_campaign import ResultState, canonical_json_bytes
from host.visible_refresh_campaign import production_profile as production
from tests import n8_bundle_fixture as legacy_fixture
from tests.test_frame_tool import ScriptedRequester
from tests.test_g1_s1_rc2g_map_baseline_once import (
    TickClock as MapTickClock,
    _responses as map_responses,
)
from tests.test_g1_s1_rc2g_quality_refresh_once import (
    TickClock as TargetTickClock,
    _responses as target_responses,
)
from tools import g1_s1_n2_physical_campaign as n2_physical
from tools import g1_s1_n8_execution_contract as frozen
from tools import g1_s1_n8_physical_execution as physical
from tools import g1_s1_rc2g_n2_photo_campaign as n2_frozen
from tools import g1_s1_rc2g_n8_once as legacy_runner
from tools import g1_s1_rc2g_n8_physical_once as runner


SCHEDULE_SECONDS = 150
PANEL = {
    "model": "MF1750-C73",
    "serial": "MF1750-LAB-PANEL-N8-0001",
    "board_id": "ESP32-C73",
    "pcb_revision": "rev-a1",
}
ANCHOR_REVIEW_BYTES = b"N8 fixture N2 physical anchor review\n"
N8_REVIEW_BYTES = b"N8 fixture 15-action physical binding review\n"
BASE_TIME = datetime(2026, 8, 8, 1, 0, tzinfo=timezone.utc)


def timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


class N8PhysicalFixture:
    """Build and execute all fifteen actions without real HTTP or device I/O."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.registry = root / "claims"
        source_file = self.write_json(
            "n2-source.json", n2_frozen.compile_campaign_manifest()
        )
        panel_file = self.write_json("panel.json", PANEL)
        anchor_review = root / "n2-anchor-review.bin"
        anchor_review.write_bytes(ANCHOR_REVIEW_BYTES)
        self.anchor = n2_physical.compile_physical_manifest_from_files(
            source_file,
            panel_file,
            anchor_review,
            minimum_interval_seconds=SCHEDULE_SECONDS,
            planned_cooldown_seconds=SCHEDULE_SECONDS,
        )["physical_campaign_contract"]
        self.binding_review_file = root / "n8-binding-review.bin"
        self.binding_review_file.write_bytes(N8_REVIEW_BYTES)
        self.context = physical.compile_n8_physical_execution_context(
            self.anchor,
            measurement_registry=legacy_fixture.measurements(),
            temperature_bin_plan=legacy_fixture.bins(),
            binding_review_bytes=N8_REVIEW_BYTES,
            minimum_interval_seconds=SCHEDULE_SECONDS,
            planned_cooldown_seconds=SCHEDULE_SECONDS,
            namespace="n8-physical-integration",
        )
        self.contract_file = self.write_json(
            "N8-PHYSICAL-EXECUTION-CONTRACT.json", self.context.contract
        )
        self.campaign_file = self.write_json(
            "N8-PHYSICAL-CAMPAIGN.json", self.context.physical_campaign
        )
        self.plan_files = runner.N8PhysicalPlanFiles(
            contract=self.contract_file,
            physical_campaign=self.campaign_file,
            binding_review_artifact=self.binding_review_file,
            minimum_interval_seconds=SCHEDULE_SECONDS,
            planned_cooldown_seconds=SCHEDULE_SECONDS,
        )
        self.reviewer_key = root / "trusted-reviewer.key"
        self.reviewer_key.write_bytes(bytes(range(32)))
        self.production_files: list[runner.N8ProductionFiles] = []
        self.production_profiles: list[production.ValidatedProductionProfile] = []
        self.result_directories: list[Path] = []
        self.bundles: list[Mapping[str, Any]] = []
        self.scripted_requests: list[ScriptedRequester] = []
        self.evaluated_ats: list[str] = []
        self.live_nows: list[str] = []
        self.observed_ats: list[str] = []

    def write_json(self, name: str, value: Any) -> Path:
        path = self.root / name
        path.write_bytes(canonical_json_bytes(value))
        return path

    def policy(
        self,
        *,
        authority_schedule_seconds: int = SCHEDULE_SECONDS,
        valid_from: str = "2026-08-08T00:30:00Z",
    ) -> dict[str, Any]:
        limits = {
            "maximum_campaign_visible_refreshes": 64,
            "maximum_session_visible_refreshes": 8,
            "maximum_consecutive_visible_refreshes": 8,
            "minimum_interval_seconds": authority_schedule_seconds,
            "minimum_cooldown_seconds": authority_schedule_seconds,
            "minimum_start_temperature_c": 0,
            "maximum_start_temperature_c": 50,
            "maximum_post_refresh_temperature_c": 50,
        }
        exact_temperature = {
            "minimum_start_temperature_c",
            "maximum_start_temperature_c",
            "maximum_post_refresh_temperature_c",
        }
        return {
            "schema_version": 1,
            "kind": production.SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND,
            "not_a_supplier_rating": True,
            "supervised_only": True,
            "automatic_execution": False,
            "automatic_retry": False,
            "automatic_recovery": False,
            "issuer": "n8-physical-test-process-owner",
            "policy_id": "n8-physical-supervised-process-policy",
            "issued_at": "2026-08-07T20:00:00Z",
            "panel_model": PANEL["model"],
            "maximum_usage_snapshot_age_seconds": 7200,
            "limits": limits,
            "validity": {
                "valid_from": valid_from,
                "expires_at": "2026-09-01T00:00:00Z",
            },
            "field_provenance": {
                field: {
                    "classification": (
                        production.EXACT_SUPPLIER_DOCUMENT_PROVENANCE
                        if field in exact_temperature
                        else production.OPERATOR_SELECTED_PROCESS_GATE_PROVENANCE
                    ),
                    "source_document_sha256": (
                        production.MF1750_A1_SOURCE_DOCUMENT_SHA256
                    ),
                }
                for field in limits
            },
        }

    def approve(
        self,
        index: int,
        *,
        last_completed_at: Optional[str],
        policy_file: Optional[Path] = None,
        evaluated_at: Optional[str] = None,
    ) -> tuple[runner.N8ProductionFiles, production.ValidatedProductionProfile]:
        row = self.context.contract["fixed_actions"][index]
        action_evaluated = (
            timestamp(BASE_TIME + timedelta(minutes=5 * index))
            if evaluated_at is None
            else evaluated_at
        )
        evaluated_datetime = datetime.fromisoformat(
            action_evaluated.replace("Z", "+00:00")
        )
        usage_file = self.write_json(
            f"action-{index + 1:02d}-usage.json",
            {
                "schema_version": 1,
                "kind": production.USAGE_EVIDENCE_KIND,
                "evidence_id": f"n8-physical-action-{index + 1:02d}-usage",
                "campaign_canonical_sha256": self.context.physical_campaign[
                    "integrity"
                ]["canonical_sha256"],
                "panel": self.context.physical_campaign["panel"],
                "firmware": self.context.physical_campaign["firmware"],
                "usage": {
                    "cumulative_visible_refresh_count": index,
                    "session_visible_refresh_count": row["ordinal"] - 1,
                    "consecutive_visible_refresh_count": row["ordinal"] - 1,
                    "last_visible_refresh_completed_at": last_completed_at,
                    "snapshot_at": timestamp(
                        evaluated_datetime - timedelta(seconds=15)
                    ),
                },
            },
        )
        selected_policy = (
            self.write_json(
                f"action-{index + 1:02d}-process-policy.json",
                self.policy(
                    valid_from=timestamp(
                        evaluated_datetime - timedelta(seconds=2)
                    )
                ),
            )
            if policy_file is None
            else policy_file
        )
        draft = production.compile_production_draft_from_files(
            campaign_file=self.campaign_file,
            firmware_binary_file=n2_frozen.FIRMWARE_BINARY,
            supplier_limits_file=selected_policy,
            usage_evidence_file=usage_file,
            profile_id="n8-physical-production-profile",
            profile_version="1.0.0",
        )
        draft_file = self.write_json(f"action-{index + 1:02d}-draft.json", draft)
        approval = production.create_production_approval(
            draft_profile_file=draft_file,
            campaign_file=self.campaign_file,
            firmware_binary_file=n2_frozen.FIRMWARE_BINARY,
            supplier_limits_file=selected_policy,
            usage_evidence_file=usage_file,
            reviewer_id="n8-physical-test-reviewer",
            reviewed_at=timestamp(
                evaluated_datetime - timedelta(seconds=5)
            ),
            reviewer_key_file=self.reviewer_key,
        )
        review_file = self.root / f"action-{index + 1:02d}-profile-review.json"
        profile_file = self.root / f"action-{index + 1:02d}-profile.json"
        production.publish_approval_bundle(
            approval,
            review_artifact_output=review_file,
            profile_output=profile_file,
        )
        files = runner.N8ProductionFiles(
            profile=profile_file,
            firmware_binary=n2_frozen.FIRMWARE_BINARY,
            limit_authority=selected_policy,
            usage_evidence=usage_file,
            review_artifact=review_file,
            reviewer_key=self.reviewer_key,
        )
        validated = physical.load_n8_physical_production_profile(
            self.context,
            profile_file=files.profile,
            campaign_file=self.campaign_file,
            firmware_binary_file=files.firmware_binary,
            limit_authority_file=files.limit_authority,
            usage_evidence_file=files.usage_evidence,
            review_artifact_file=files.review_artifact,
            reviewer_key_file=files.reviewer_key,
            evaluated_at=action_evaluated,
        )
        return files, validated

    @staticmethod
    def confirmations(snapshot: frozen.N8ActionSnapshot) -> dict[str, bool]:
        return {
            field: True for field in legacy_runner._confirmation_fields(snapshot)
        }

    @staticmethod
    def requester(
        snapshot: frozen.N8ActionSnapshot,
        prior_bundle: Optional[Mapping[str, Any]],
    ) -> tuple[ScriptedRequester, Any]:
        if prior_bundle is None:
            return ScriptedRequester(map_responses()), MapTickClock()
        completed = prior_bundle["evidence"]["protocol_evidence"][
            "completed_action"
        ]
        contract = frozen.build_n8_protocol_contract(
            snapshot,
            prior_job_id=completed["job_id"],
            prior_operation_id=completed["operation_id"],
        )
        responses = target_responses(snapshot.frame, contract)
        responses["/api/job"][0] = (200, json.dumps(completed["job_raw"]))
        responses["/api/diagnostic/report"][0] = (
            200,
            json.dumps(completed["diagnostic_raw"]),
        )
        return ScriptedRequester(responses), TargetTickClock()

    def run_all(self) -> None:
        if self.bundles:
            raise RuntimeError("N8 physical fixture may run only once")
        prior_results: list[Path] = []
        prior_bundle: Optional[Mapping[str, Any]] = None
        previous_sequence: Optional[str] = None
        previous_global_completed_at: Optional[str] = None
        for index, row in enumerate(self.context.contract["fixed_actions"]):
            if row["sequence_id"] != previous_sequence:
                prior_results = []
                prior_bundle = None
                previous_sequence = row["sequence_id"]
            snapshot = physical.load_n8_physical_action_snapshot(
                self.context, row["action_key"]
            )
            evaluated_at = timestamp(BASE_TIME + timedelta(minutes=5 * index))
            live_now = timestamp(
                BASE_TIME + timedelta(minutes=5 * index, seconds=30)
            )
            observed_at = timestamp(
                BASE_TIME + timedelta(minutes=5 * index, seconds=60)
            )
            files, validated = self.approve(
                index, last_completed_at=previous_global_completed_at
            )
            scripted, clock = self.requester(snapshot, prior_bundle)
            destination = self.root / f"result-{index + 1:02d}-{row['action_key']}"
            with (
                mock.patch.object(
                    legacy_runner._fixed,
                    "DEFAULT_CLAIM_REGISTRY",
                    self.registry,
                ),
                mock.patch.object(runner, "http_request", scripted),
            ):
                runner.run_n8_physical_action_once(
                    row["action_key"],
                    destination,
                    "http://fake-device",
                    plan_files=self.plan_files,
                    production_files=files,
                    evaluated_at=evaluated_at,
                    authorization_confirmation=(
                        runner.required_authorization_confirmation(
                            self.context, row["action_key"]
                        )
                    ),
                    panel_confirmation=runner.required_panel_confirmation(
                        self.context
                    ),
                    profile_confirmation=(
                        runner.required_production_profile_confirmation(
                            validated
                        )
                    ),
                    start_external_temperature_c=(
                        legacy_fixture._temperature_for(snapshot)
                    ),
                    prior_result_files=tuple(prior_results),
                    confirmations=self.confirmations(snapshot),
                    sleeper=lambda _seconds: None,
                    clock=clock,
                    wall_clock=lambda value=live_now: value,
                )
                runtime = physical.compile_n8_physical_runtime_manifest(
                    self.context, validated
                )
                observation = legacy_fixture.operator_observation(
                    snapshot,
                    root=self.root,
                    runtime=runtime,
                    state=ResultState.PASS,
                    score_offset=index / 100,
                    overrides={"observed_at": observed_at},
                )
                observation_file = self.write_json(
                    f"action-{index + 1:02d}-operator-observation.json",
                    observation,
                )
                runner.finalize_n8_physical_observation(
                    destination,
                    observation_file,
                    reviewer_key_file=self.reviewer_key,
                    prior_result_files=tuple(prior_results),
                )
            bundle = json.loads(
                (destination / runner.BUNDLE_FILENAME).read_text(
                    encoding="utf-8"
                )
            )
            result_file = destination / runner.P0_RESULT_FILENAME
            self.production_files.append(files)
            self.production_profiles.append(validated)
            self.result_directories.append(destination)
            self.bundles.append(bundle)
            self.scripted_requests.append(scripted)
            self.evaluated_ats.append(evaluated_at)
            self.live_nows.append(live_now)
            self.observed_ats.append(observed_at)
            prior_results.append(result_file)
            prior_bundle = bundle
            previous_global_completed_at = observed_at


__all__ = [
    "BASE_TIME",
    "N8PhysicalFixture",
    "PANEL",
    "SCHEDULE_SECONDS",
    "timestamp",
]
