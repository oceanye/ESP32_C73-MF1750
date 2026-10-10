from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.application.n6_browser_campaign import (
    DEFAULT_MAPPINGS,
    build_n6_offline_manifest,
)
from host.application import (
    InputSource,
    SimulationOptions,
    decode_normalized_source,
    prepare_simulation_artifact,
    simulate_panel,
)
from host.application.n6_physical_execution import (
    EXTERNAL_AUTHORIZATION_ROLE,
    FORMAL_REVIEW_ROLE,
    N6N5PhysicalPaletteEvidence,
    N6PhysicalBrowserController,
    N6PhysicalExecutionError,
    N6PhysicalPostClaimUnknown,
    N6PhysicalReceiptPaths,
    N6PhysicalReceiptStore,
    N6PhysicalSources,
    N6ProductionProfileFiles,
    N6RuntimeEvidenceFiles,
    N6StaticEvidenceFiles,
    RUNTIME_OBSERVATION_ROLE,
    RUNTIME_REVIEW_ROLE,
    authorization_binding,
    compile_n6_physical_context,
    finalize_n6_physical_manual_observation,
    materialize_n6_physical_manifest,
    required_n6_action_authorization,
    required_n6_panel_plan_confirmation,
    required_n6_profile_confirmation,
    runtime_control_binding,
    sign_n6_authenticated_evidence,
    static_review_binding,
    validate_n6_physical_finalized_bundle,
    validate_n6_physical_manifest,
    validate_n6_physical_postclaim_incident,
    validate_n6_physical_receipt,
    validate_n6_physical_receipt_durable_commit,
)
import host.application.n6_physical_execution as n6_physical
from host.application.durable_io import write_new_bytes_durable
from host.application.n6_visible_execution import (
    AUTHORIZATION_KIND,
    FORMAL_ARTIFACT_REVIEW_KIND,
    MANUAL_OBSERVATION_KIND,
    N6_ARM_CONFIRMATION,
    RUNTIME_OBSERVATION_KIND,
    RUNTIME_REVIEW_KIND,
    AtomicN6ClaimStore,
    N6ClaimConsumed,
    N6HttpRefreshDriver,
    N6VisibleExecutionError,
    seal_n6_external_authorization,
    seal_n6_formal_artifact_review,
    seal_n6_manual_observation,
    seal_n6_runtime_observation,
    seal_n6_runtime_review,
)
from tests.application_browser_harness import LoopbackFakeDeviceServer
from tools import mf1750_frame_tool as frame_tool
from host.visible_refresh_campaign import (
    CAMPAIGN_KIND,
    build_fixed_action_declaration,
    build_session_contract,
    canonical_json_bytes,
    result_file_sha256,
    seal_campaign_contract,
)
from host.visible_refresh_campaign import production_profile as production
from host.extended_color import aggregation as n5_aggregation
from host.extended_color import execution as n5_execution
from host.color_pipeline import palette_from_mapping
from host.gamut_mapping import (
    build_synthetic_reference_profile,
    gamut_profile_from_mapping,
    seal_profile_mapping,
)
from tests import n6_formal_fixture as legacy_fixture
from tests.n5_physical_palette_fixture import cached_physical_palette_fixture


MATERIALIZED_AT = "2026-08-08T12:03:20+08:00"
OBSERVED_AT = "2026-08-08T12:04:00+08:00"
INITIAL_LIVE_AT = "2026-08-08T12:04:30+08:00"
CLAIMED_AT = "2026-08-08T12:04:31+08:00"
COMPLETED_AT = "2026-08-08T12:04:32+08:00"
PHYSICAL_PANEL = {
    "model": legacy_fixture.PANEL["model"],
    "serial": "MF1750-PHYSICAL-PANEL-0006",
    "board_id": "ESP32-C73-BOARD-0006",
    "pcb_revision": "rev-a1",
}
PHYSICAL_FIRMWARE_BYTES = b"n6-physical-rc2g-test-firmware\x00" * 128
PHYSICAL_FIRMWARE = {
    **legacy_fixture.FIRMWARE,
    "binary_sha256": hashlib.sha256(PHYSICAL_FIRMWARE_BYTES).hexdigest(),
}


def _write_json(path: Path, value: object) -> Path:
    path.write_bytes(canonical_json_bytes(value))
    return path


@lru_cache(maxsize=1)
def _physical_artifact_and_profile():
    n5_palette = cached_physical_palette_fixture(
        panel=PHYSICAL_PANEL,
        firmware=PHYSICAL_FIRMWARE,
        firmware_bytes=PHYSICAL_FIRMWARE_BYTES,
    )
    palette = palette_from_mapping(n5_palette.inner_aggregate["palette"])
    gamut_payload = build_synthetic_reference_profile().canonical_mapping()
    gamut_payload.pop("canonical_sha256")
    gamut_payload["profile_id"] = "n6-physical-measured-mixtures-v1"
    gamut_payload["palette"] = {
        "id": palette.palette_id,
        "canonical_sha256": palette.canonical_sha256,
    }
    gamut_payload["model"].update(
        {
            "kind": "measured_point_cloud_v1",
            "characterization_level": "measured_mixtures",
            "approximation": False,
            "mixture_samples": [
                {
                    "sample_id": "n6-physical-mix-black-white",
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
    for index, item in enumerate(gamut_payload["model"]["pure_sample_refs"]):
        item["artifact_sha256"] = f"{index + 20:064x}"
    gamut_payload["measurement"].update(
        {
            "measurement_id": "n6-physical-gamut-measurement",
            "raw_artifact_sha256": "7" * 64,
            "geometry": "45/0",
            "backing": "white calibrated backing",
            "instrument": "structural-test-spectrophotometer",
            "instrument_calibration_date": "2026-01-01",
            "measured_at": "2026-08-08T10:00:00+08:00",
        }
    )
    gamut_payload["panel"] = {
        "model": PHYSICAL_PANEL["model"],
        "panel_id": PHYSICAL_PANEL["serial"],
        "batch": "MF1750-PHYSICAL-BATCH-0006",
    }
    gamut_payload["firmware"].update(
        {
            "commit": PHYSICAL_FIRMWARE["source_commit"],
            "waveform_version": "n6-physical-waveform-v1",
        }
    )
    gamut_payload["environment"].update(
        {
            "temperature_c": 25.0,
            "temperature_tolerance_c": 2.0,
            "relative_humidity_percent": 50.0,
        }
    )
    gamut_payload["trust"].update(
        {
            "source_statement": "N5 physical cross-stage structural test evidence",
            "signature": "test-only-not-a-production-signature",
        }
    )
    gamut_profile_mapping = seal_profile_mapping(gamut_payload)
    gamut = gamut_profile_from_mapping(gamut_profile_mapping, palette)
    source_bytes = legacy_fixture.source_png()
    decoded = decode_normalized_source(
        source_bytes, "image/png", "contain", rotation_degrees=0
    )
    simulation = simulate_panel(
        decoded.raster,
        palette=palette,
        profile=gamut,
        options=SimulationOptions(algorithm="none"),
    )
    artifact = prepare_simulation_artifact(
        simulation,
        InputSource(
            "browser-selected-image",
            "image/png",
            hashlib.sha256(source_bytes).hexdigest(),
            "server-recomputed SHA256 of original selected file bytes",
        ),
        decode_provenance=decoded.provenance,
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
                "id": gamut.profile_id,
                "canonical_sha256": gamut.canonical_sha256,
                "characterization_level": gamut.characterization_level,
                "hardware_formal_qualified": False,
            }
        ],
        "formal_eligibility": {"eligible": False},
    }
    return artifact, config, gamut_profile_mapping, palette


class SequenceClock:
    def __init__(self, *values: str) -> None:
        self.values = list(values)
        self.index = 0

    def __call__(self) -> str:
        if self.index >= len(self.values):
            return self.values[-1]
        value = self.values[self.index]
        self.index += 1
        return value


class RecordingDriver:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls = 0

    def __call__(self, frame: bytes, mappings):
        del frame, mappings
        self.calls += 1
        return deepcopy(self.result)


class InterruptingDriver:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, frame: bytes, mappings):
        del frame, mappings
        self.calls += 1
        raise KeyboardInterrupt("synthetic post-claim interrupt")


class N6PhysicalFixture:
    def __init__(
        self,
        root: Path,
        *,
        last_visible_refresh: str = "2026-08-08T12:00:00+08:00",
        minimum_interval_seconds: float = 120,
        authority_interval_seconds: float = 10,
        application_origin: str = "http://127.0.0.1:8765",
    ) -> None:
        self.root = root
        self.application_origin = application_origin
        self.key_bytes = bytes(range(32))
        self.key_file = root / "trusted-reviewer.key"
        self.key_file.write_bytes(self.key_bytes)
        self.firmware_bytes = PHYSICAL_FIRMWARE_BYTES
        self.firmware_file = root / "firmware.bin"
        self.firmware_file.write_bytes(self.firmware_bytes)
        self.firmware = deepcopy(PHYSICAL_FIRMWARE)
        artifact, config, self.gamut_profile_mapping, self.measured_palette = (
            _physical_artifact_and_profile()
        )
        self.artifact = artifact
        self.offline = build_n6_offline_manifest(
            artifact,
            config,
            panel=PHYSICAL_PANEL,
            firmware=self.firmware,
            campaign_id="n6-physical-source-campaign",
            session_id="n6-physical-session",
            cell_id="n6-physical-cell",
            action_id="n6-physical-visible-action",
        )
        source_action = self.offline["p0_campaign"]["actions"][0]
        anchor_action = build_fixed_action_declaration(
            campaign_id="n6-real-physical-anchor",
            session_id="n6-anchor-session",
            cell_id="n6-anchor-cell",
            action_id="n6-anchor-observation",
            phase="physical-panel-anchor",
            frame=source_action["identity"]["frame"],
        )
        anchor_session = build_session_contract(
            session_id="n6-anchor-session",
            cell_id="n6-anchor-cell",
            power_mode="controller_fresh_boot",
            planned_cooldown_seconds=0,
            final_power_off_required=False,
            action_identity_sha256s=[anchor_action["action_identity_sha256"]],
        )
        self.anchor = seal_campaign_contract(
            {
                "schema_version": 1,
                "kind": CAMPAIGN_KIND,
                "campaign_id": "n6-real-physical-anchor",
                "panel": PHYSICAL_PANEL,
                "firmware": self.firmware,
                "actions": [anchor_action],
                "sessions": [anchor_session],
                "classification": deepcopy(
                    self.offline["p0_campaign"]["classification"]
                ),
            }
        )
        self.anchor_file = _write_json(root / "physical-anchor.json", self.anchor)
        self.binding_review_bytes = (
            b"N6 physical panel/firmware binding reviewed test evidence\n"
        )
        n5_palette = cached_physical_palette_fixture(
            panel=PHYSICAL_PANEL,
            firmware=PHYSICAL_FIRMWARE,
            firmware_bytes=PHYSICAL_FIRMWARE_BYTES,
        )
        self.sources = N6PhysicalSources(
            offline_manifest=self.offline,
            physical_anchor_campaign=self.anchor,
            physical_anchor_campaign_file=self.anchor_file,
            binding_review_bytes=self.binding_review_bytes,
            minimum_interval_seconds=minimum_interval_seconds,
            planned_cooldown_seconds=60,
            palette_aggregate=n5_palette.aggregate_envelope,
            palette_aggregate_file=n5_palette.aggregate_file,
            n5_physical_palette=N6N5PhysicalPaletteEvidence(
                context=n5_palette.context,
                observations=n5_palette.observations,
                observation_files=n5_palette.observation_files,
                standard_table=n5_palette.standard_table,
                standard_table_file=n5_palette.standard_table_file,
                instrument_qualification=n5_palette.instrument_qualification,
                instrument_qualification_file=(
                    n5_palette.instrument_qualification_file
                ),
                finalized_bundle=n5_palette.finalized_bundle,
                finalized_bundle_file=n5_palette.finalized_bundle_file,
                result_dirs=n5_palette.result_dirs,
                profile_reviewer_key_file=(
                    n5_palette.profile_reviewer_key_file
                ),
            ),
            gamut_profile=self.gamut_profile_mapping,
            prior_result=legacy_fixture.prior_result(),
            prior_result_sha256=result_file_sha256(legacy_fixture.prior_result()),
        )
        self.context = compile_n6_physical_context(self.sources)
        self.campaign = self.context["physical_rebind"]["physical_campaign"]
        self.campaign_file = _write_json(root / "physical-campaign.json", self.campaign)
        self.authority = {
            "schema_version": 1,
            "kind": production.SUPPLIER_LIMITS_KIND,
            "supplier_id": "n6-test-limit-authority",
            "document_id": "n6-test-limits-2026-08-08",
            "issued_at": "2026-08-08T10:00:00+08:00",
            "panel_model": PHYSICAL_PANEL["model"],
            "maximum_usage_snapshot_age_seconds": 3600,
            "limits": {
                "maximum_campaign_visible_refreshes": 20,
                "maximum_session_visible_refreshes": 10,
                "maximum_consecutive_visible_refreshes": 10,
                "minimum_interval_seconds": authority_interval_seconds,
                "minimum_cooldown_seconds": 5,
                "minimum_start_temperature_c": 10,
                "maximum_start_temperature_c": 40,
                "maximum_post_refresh_temperature_c": 45,
            },
            "validity": {
                "valid_from": "2026-08-08T12:03:15+08:00",
                "expires_at": "2026-08-08T14:00:00+08:00",
            },
        }
        self.authority_file = _write_json(root / "limit-authority.json", self.authority)
        snapshot_at = max(
            last_visible_refresh,
            "2026-08-08T12:03:05+08:00",
        )
        self.usage = {
            "schema_version": 1,
            "kind": production.USAGE_EVIDENCE_KIND,
            "evidence_id": "n6-physical-usage-before-action",
            "campaign_canonical_sha256": self.campaign["integrity"][
                "canonical_sha256"
            ],
            "panel": self.campaign["panel"],
            "firmware": self.campaign["firmware"],
            "usage": {
                "cumulative_visible_refresh_count": 1,
                "session_visible_refresh_count": 1,
                "consecutive_visible_refresh_count": 1,
                "last_visible_refresh_completed_at": last_visible_refresh,
                "snapshot_at": snapshot_at,
            },
        }
        self.usage_file = _write_json(root / "usage.json", self.usage)
        self.draft_file = root / "profile-draft.json"
        draft = production.compile_production_draft_from_files(
            campaign_file=self.campaign_file,
            firmware_binary_file=self.firmware_file,
            supplier_limits_file=self.authority_file,
            usage_evidence_file=self.usage_file,
            profile_id="n6-physical-production-profile",
            profile_version="1.0.0",
        )
        _write_json(self.draft_file, draft)
        approval = production.create_production_approval(
            draft_profile_file=self.draft_file,
            campaign_file=self.campaign_file,
            firmware_binary_file=self.firmware_file,
            supplier_limits_file=self.authority_file,
            usage_evidence_file=self.usage_file,
            reviewer_id="n6-physical-trusted-reviewer",
            reviewed_at="2026-08-08T12:03:10+08:00",
            reviewer_key_file=self.key_file,
        )
        self.profile_file = root / "profile.json"
        self.profile_review_file = root / "profile-review.json"
        self.profile_file.write_bytes(approval.profile_bytes)
        self.profile_review_file.write_bytes(approval.review_artifact_bytes)
        self.production_files = N6ProductionProfileFiles(
            profile_file=self.profile_file,
            campaign_file=self.campaign_file,
            firmware_binary_file=self.firmware_file,
            limit_authority_file=self.authority_file,
            usage_evidence_file=self.usage_file,
            review_artifact_file=self.profile_review_file,
            reviewer_key_file=self.key_file,
        )
        self.production = production.load_validated_production_profile(
            profile_file=self.profile_file,
            campaign_file=self.campaign_file,
            firmware_binary_file=self.firmware_file,
            supplier_limits_file=self.authority_file,
            usage_evidence_file=self.usage_file,
            review_artifact_file=self.profile_review_file,
            reviewer_key_file=self.key_file,
            evaluated_at=MATERIALIZED_AT,
        )
        self.formal_evidence = b"reviewed N6 four-preview artifact evidence\n"
        self.runtime_review_evidence = b"reviewed Chromium/runtime envelope evidence\n"
        self.formal_evidence_file = root / "formal-review-evidence.bin"
        self.runtime_review_evidence_file = root / "runtime-review-evidence.bin"
        self.formal_evidence_file.write_bytes(self.formal_evidence)
        self.runtime_review_evidence_file.write_bytes(self.runtime_review_evidence)
        offline = self.context["physical_offline_manifest"]
        source = offline["source_artifact"]
        self.runtime_review = seal_n6_runtime_review(
            {
                "schema_version": 1,
                "kind": RUNTIME_REVIEW_KIND,
                "runtime_id": "n6-physical-reviewed-runtime",
                "application_build": {
                    "source_commit": legacy_fixture.SOURCE_COMMIT,
                    "bundle_sha256": legacy_fixture.APPLICATION_BUILD_SHA256,
                },
                "firmware": self.firmware,
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
                    "reviewer_id": "n6-physical-runtime-reviewer",
                    "reviewed_at": "2026-08-08T12:03:12+08:00",
                    "review_artifact_sha256": hashlib.sha256(
                        self.runtime_review_evidence
                    ).hexdigest(),
                },
            }
        )
        self.formal_review = seal_n6_formal_artifact_review(
            {
                "schema_version": 1,
                "kind": FORMAL_ARTIFACT_REVIEW_KIND,
                "review_id": "n6-physical-formal-artifact-review",
                "offline_manifest_canonical_sha256": offline["integrity"][
                    "canonical_sha256"
                ],
                "artifact_identity": source["artifact_identity"],
                "source_input_sha256": source["input"]["sha256"],
                "four_preview_sha256": {
                    stage: source["previews"][stage]["sha256"]
                    for stage in ("source", "mapped", "final", "model")
                },
                "palette_aggregate_canonical_sha256": n5_palette.inner_aggregate[
                    "integrity"
                ]["canonical_sha256"],
                "palette_canonical_sha256": self.measured_palette.canonical_sha256,
                "gamut_profile_canonical_sha256": self.sources.gamut_profile[
                    "canonical_sha256"
                ],
                "panel": self.campaign["panel"],
                "firmware": self.campaign["firmware"],
                "application_build_sha256": legacy_fixture.APPLICATION_BUILD_SHA256,
                "review": {
                    "approved": True,
                    "reviewer_id": "n6-physical-formal-reviewer",
                    "reviewed_at": "2026-08-08T12:03:14+08:00",
                    "review_artifact_sha256": hashlib.sha256(
                        self.formal_evidence
                    ).hexdigest(),
                },
            }
        )
        self.formal_envelope = sign_n6_authenticated_evidence(
            self.formal_review,
            role=FORMAL_REVIEW_ROLE,
            evidence_bytes=self.formal_evidence,
            binding=static_review_binding(
                self.context, self.production, role=FORMAL_REVIEW_ROLE
            ),
            trusted_reviewer_key=self.key_bytes,
        )
        self.runtime_review_envelope = sign_n6_authenticated_evidence(
            self.runtime_review,
            role=RUNTIME_REVIEW_ROLE,
            evidence_bytes=self.runtime_review_evidence,
            binding=static_review_binding(
                self.context, self.production, role=RUNTIME_REVIEW_ROLE
            ),
            trusted_reviewer_key=self.key_bytes,
        )
        self.static_files = N6StaticEvidenceFiles(
            formal_review_evidence_file=self.formal_evidence_file,
            runtime_review_evidence_file=self.runtime_review_evidence_file,
            trusted_reviewer_key_file=self.key_file,
        )
        self.manifest = materialize_n6_physical_manifest(
            self.context,
            sources=self.sources,
            production_files=self.production_files,
            static_evidence_files=self.static_files,
            formal_review_envelope=self.formal_envelope,
            runtime_review_envelope=self.runtime_review_envelope,
            materialized_at=MATERIALIZED_AT,
        )
        self.authorization_evidence = b"external one-visible authorization evidence\n"
        self.authorization_evidence_file = root / "authorization-evidence.bin"
        self.authorization_evidence_file.write_bytes(self.authorization_evidence)
        legacy_manifest = self.manifest["legacy_formal_manifest"]
        self.authorization = seal_n6_external_authorization(
            {
                "schema_version": 1,
                "kind": AUTHORIZATION_KIND,
                "authorization_id": "n6-physical-one-visible-auth",
                "formal_manifest_canonical_sha256": legacy_manifest["integrity"][
                    "canonical_sha256"
                ],
                "action_identity_sha256": legacy_manifest["action"][
                    "action_identity_sha256"
                ],
                "prior_result_file_sha256": legacy_manifest["prior_binding"][
                    "result_file_sha256"
                ],
                "issued_at": "2026-08-08T12:03:30+08:00",
                "expires_at": "2026-08-08T13:00:00+08:00",
                "operator_id": "n6-physical-operator",
                "authorization_artifact_sha256": hashlib.sha256(
                    self.authorization_evidence
                ).hexdigest(),
                "confirmation_sha256": hashlib.sha256(
                    N6_ARM_CONFIRMATION.encode("utf-8")
                ).hexdigest(),
                "maximum_frame_posts": 1,
                "automatic_retry_authorized": False,
                "automatic_recovery_authorized": False,
            },
            manifest=legacy_manifest,
        )
        self.authorization_envelope = sign_n6_authenticated_evidence(
            self.authorization,
            role=EXTERNAL_AUTHORIZATION_ROLE,
            evidence_bytes=self.authorization_evidence,
            binding=authorization_binding(self.manifest),
            trusted_reviewer_key=self.key_bytes,
        )
        self.runtime_evidence = b"live voltage/current/temperature/operator evidence\n"
        self.runtime_evidence_file = root / "runtime-observation-evidence.bin"
        self.runtime_evidence_file.write_bytes(self.runtime_evidence)
        control = runtime_control_binding(
            self.manifest,
            self.authorization_envelope,
            self.production,
            observed_at=OBSERVED_AT,
        )
        self.runtime_observation = seal_n6_runtime_observation(
            {
                "schema_version": 1,
                "kind": RUNTIME_OBSERVATION_KIND,
                "formal_manifest_canonical_sha256": legacy_manifest["integrity"][
                    "canonical_sha256"
                ],
                "observed_at": OBSERVED_AT,
                "controller_voltage_v": 3.3,
                "idle_current_a": 0.001,
                "start_temperature_c": 25.0,
                "supply_3v3_normal": True,
                "supply_cv_current_normal": True,
                "j2_on": True,
                "physical_cutoff_available": True,
                "operator_present": True,
                "application_origin": self.application_origin,
                "operator_gate_artifact_sha256": hashlib.sha256(
                    canonical_json_bytes(control)
                ).hexdigest(),
                "runtime_evidence_sha256": hashlib.sha256(
                    self.runtime_evidence
                ).hexdigest(),
            },
            manifest=legacy_manifest,
        )
        self.runtime_observation_envelope = sign_n6_authenticated_evidence(
            self.runtime_observation,
            role=RUNTIME_OBSERVATION_ROLE,
            evidence_bytes=self.runtime_evidence,
            binding=control,
            trusted_reviewer_key=self.key_bytes,
        )
        self.runtime_files = N6RuntimeEvidenceFiles(
            authorization_evidence_file=self.authorization_evidence_file,
            runtime_observation_evidence_file=self.runtime_evidence_file,
            trusted_reviewer_key_file=self.key_file,
        )

    def controller(
        self,
        workspace: Path,
        driver: N6HttpRefreshDriver,
        *,
        clock: SequenceClock | None = None,
        runtime_files: N6RuntimeEvidenceFiles | None = None,
        receipt_tag: str = "recorded-physical-receipt",
    ) -> N6PhysicalBrowserController:
        claim_store = AtomicN6ClaimStore(workspace)
        claim_store.prepare_registry(self.manifest["legacy_formal_manifest"])
        claim_path = claim_store.claim_path(self.manifest["legacy_formal_manifest"])
        receipt_paths = N6PhysicalReceiptPaths(
            receipt_output=workspace / f"{receipt_tag}.json",
            receipt_commit_output=workspace / f"{receipt_tag}.commit.json",
            incident_output=claim_path.parent
            / f"{claim_path.name}.N6-PHYSICAL-UNKNOWN.json",
        )
        recording_sink = N6PhysicalReceiptStore(
            self.manifest, paths=receipt_paths
        )

        return N6PhysicalBrowserController(
            self.manifest,
            sources=self.sources,
            production_files=self.production_files,
            static_evidence_files=self.static_files,
            authorization_envelope=self.authorization_envelope,
            runtime_observation_envelope=self.runtime_observation_envelope,
            runtime_evidence_files=runtime_files or self.runtime_files,
            claim_store=claim_store,
            protocol_driver=driver,
            attempt_id="n6-physical-attempt-1",
            post_claim_receipt_sink=recording_sink,
            utc_now=clock
            or SequenceClock(INITIAL_LIVE_AT, CLAIMED_AT, COMPLETED_AT),
        )

    def prepare_browser(self, controller: N6PhysicalBrowserController) -> None:
        controller.bind_server_origin(self.application_origin)
        controller.record_page_load()
        controller.record_authenticated_read()
        if not controller.observe_artifact(self.artifact):
            raise AssertionError("physical N6 fixture artifact was rejected")
        report_sha = self.artifact.identity["report_sha256"]
        for stage in ("source", "mapped", "final", "model"):
            controller.record_preview_fetch(report_sha, stage)
        controller.allow_connection(token_validated=True, same_origin_validated=True)
        controller.local_preflight(
            DEFAULT_MAPPINGS,
            token_validated=True,
            same_origin_validated=True,
        )

    def arm(self, controller: N6PhysicalBrowserController) -> None:
        controller.arm(
            required_n6_action_authorization(self.manifest),
            panel_plan_confirmation=required_n6_panel_plan_confirmation(
                self.manifest
            ),
            profile_confirmation=required_n6_profile_confirmation(self.manifest),
            token_validated=True,
            same_origin_validated=True,
        )


class N6PhysicalProductionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _idle_http_driver(self) -> N6HttpRefreshDriver:
        return N6HttpRefreshDriver("http://127.0.0.1:9")

    def _success_http_driver(self) -> N6HttpRefreshDriver:
        server = LoopbackFakeDeviceServer().start()
        server.mode = "success"
        self.addCleanup(server.close)
        return N6HttpRefreshDriver(
            server.origin,
            poll_interval_s=0.001,
            sleeper=lambda _seconds: None,
        )

    def _interrupt_after_post_http_driver(self) -> N6HttpRefreshDriver:
        server = LoopbackFakeDeviceServer().start()
        server.mode = "success"
        self.addCleanup(server.close)

        def requester(base_url: str, endpoint: str, **kwargs):
            if endpoint == "/api/frame" and kwargs.get("method") == "POST":
                raise KeyboardInterrupt("synthetic post-claim POST interrupt")
            return frame_tool.http_request(base_url, endpoint, **kwargs)

        return N6HttpRefreshDriver(
            server.origin,
            requester=requester,
            poll_interval_s=0.001,
            sleeper=lambda _seconds: None,
        )

    def _claim_consumed_requester_driver(self) -> N6HttpRefreshDriver:
        def requester(_base_url: str, _endpoint: str, **_kwargs):
            raise N6ClaimConsumed("synthetic requester exception after claim")

        return N6HttpRefreshDriver(
            "http://127.0.0.1:9",
            requester=requester,
            poll_interval_s=0.001,
            sleeper=lambda _seconds: None,
        )

    def test_materialization_rotates_action_and_claim_and_deep_validates(self) -> None:
        fixture = N6PhysicalFixture(self.root)
        validated = validate_n6_physical_manifest(
            fixture.manifest,
            sources=fixture.sources,
            production_files=fixture.production_files,
            static_evidence_files=fixture.static_files,
            evaluated_at=INITIAL_LIVE_AT,
        )
        rotation = validated["physical_context"]["identity_rotation"]
        self.assertNotEqual(
            rotation["source_action_identity_sha256"],
            rotation["physical_action_identity_sha256"],
        )
        self.assertNotEqual(
            rotation["source_claim_filename"], rotation["physical_claim_filename"]
        )
        self.assertTrue(validated["operator_schedule"]["not_a_supplier_rating"])
        self.assertFalse(validated["classification"]["hardware_qualification_claimed"])

    def test_core_only_and_self_resealed_n5_palette_are_rejected(self) -> None:
        fixture = N6PhysicalFixture(self.root)
        core_file = _write_json(
            self.root / "core-only-palette.json",
            fixture.sources.palette_aggregate["aggregate"],
        )
        core_only = replace(
            fixture.sources,
            palette_aggregate=fixture.sources.palette_aggregate["aggregate"],
            palette_aggregate_file=core_file,
        )
        with self.assertRaisesRegex(
            N6PhysicalExecutionError, "physical palette aggregate envelope|core-only"
        ):
            compile_n6_physical_context(core_only)

        forged = deepcopy(fixture.sources.palette_aggregate)
        forged.pop("integrity")
        forged_inner = forged["aggregate"]
        forged_inner.pop("integrity")
        forged_inner["statistics"]["attacker_resealed_statistic"] = {
            "note": "not derived from raw observations"
        }
        forged["aggregate"] = {
            **forged_inner,
            "integrity": n5_aggregation._integrity(forged_inner),  # noqa: SLF001
        }
        forged = n5_execution._seal(forged)  # noqa: SLF001
        forged_file = _write_json(self.root / "forged-physical-palette.json", forged)
        forged_sources = replace(
            fixture.sources,
            palette_aggregate=forged,
            palette_aggregate_file=forged_file,
        )
        with self.assertRaisesRegex(
            N6PhysicalExecutionError, "raw-observation reconstruction"
        ):
            compile_n6_physical_context(forged_sources)

        evidence = fixture.sources.n5_physical_palette
        missing = replace(
            evidence,
            observations=evidence.observations[:-1],
            observation_files=evidence.observation_files[:-1],
        )
        duplicated = replace(
            evidence,
            observation_files=(
                *evidence.observation_files[:-1],
                evidence.observation_files[0],
            ),
        )
        wrong_standard = replace(
            evidence,
            standard_table=evidence.instrument_qualification,
            standard_table_file=evidence.instrument_qualification_file,
        )
        wrong_instrument = replace(
            evidence,
            instrument_qualification=evidence.standard_table,
            instrument_qualification_file=evidence.standard_table_file,
        )
        missing_result = replace(evidence, result_dirs=evidence.result_dirs[:-1])
        for label, attacked in (
            ("missing-observation", missing),
            ("duplicate-observation-file", duplicated),
            ("wrong-standard-table", wrong_standard),
            ("wrong-instrument-qualification", wrong_instrument),
            ("missing-result-directory", missing_result),
        ):
            with self.subTest(attack=label):
                with self.assertRaises(N6PhysicalExecutionError):
                    compile_n6_physical_context(
                        replace(fixture.sources, n5_physical_palette=attacked)
                    )

    def test_cross_panel_manifest_is_rejected(self) -> None:
        fixture = N6PhysicalFixture(self.root)
        wrong_anchor_payload = deepcopy(fixture.anchor)
        wrong_anchor_payload.pop("integrity")
        wrong_anchor_payload["panel"]["serial"] = "MF1750-PHYSICAL-PANEL-9999"
        wrong_anchor = seal_campaign_contract(wrong_anchor_payload)
        wrong_anchor_file = _write_json(
            self.root / "wrong-physical-anchor.json", wrong_anchor
        )
        wrong_sources = N6PhysicalSources(
            **{
                **fixture.sources.__dict__,
                "physical_anchor_campaign": wrong_anchor,
                "physical_anchor_campaign_file": wrong_anchor_file,
            }
        )
        with self.assertRaises(N6PhysicalExecutionError):
            validate_n6_physical_manifest(
                fixture.manifest,
                sources=wrong_sources,
                production_files=fixture.production_files,
                static_evidence_files=fixture.static_files,
                evaluated_at=INITIAL_LIVE_AT,
            )
    def test_forged_review_and_wrong_key_are_rejected(self) -> None:
        fixture = N6PhysicalFixture(self.root)
        forged = deepcopy(fixture.manifest)
        review = forged["authenticated_static_reviews"]["formal_artifact_review"]
        forged_record = deepcopy(review["record"])
        forged_record.pop("integrity")
        forged_record["review"]["reviewer_id"] = "forged-reviewer"
        review["record"] = seal_n6_formal_artifact_review(forged_record)
        review["record_canonical_sha256"] = hashlib.sha256(
            canonical_json_bytes(review["record"])
        ).hexdigest()
        with self.assertRaises(N6PhysicalExecutionError):
            validate_n6_physical_manifest(
                forged,
                sources=fixture.sources,
                production_files=fixture.production_files,
                static_evidence_files=fixture.static_files,
                evaluated_at=INITIAL_LIVE_AT,
            )
        wrong_key = self.root / "wrong-reviewer.key"
        wrong_key.write_bytes(bytes(range(1, 33)))
        wrong_runtime_files = N6RuntimeEvidenceFiles(
            authorization_evidence_file=fixture.authorization_evidence_file,
            runtime_observation_evidence_file=fixture.runtime_evidence_file,
            trusted_reviewer_key_file=wrong_key,
        )
        driver = self._idle_http_driver()
        with self.assertRaises(N6PhysicalExecutionError):
            fixture.controller(self.root, driver, runtime_files=wrong_runtime_files)
        self.assertEqual(driver.total_request_count, 0)
        fixture.formal_evidence_file.write_bytes(b"different review evidence bytes\n")
        with self.assertRaises(N6PhysicalExecutionError):
            validate_n6_physical_manifest(
                fixture.manifest,
                sources=fixture.sources,
                production_files=fixture.production_files,
                static_evidence_files=fixture.static_files,
                evaluated_at=INITIAL_LIVE_AT,
            )
        fixture.formal_evidence_file.write_bytes(fixture.formal_evidence)
        fixture.authorization_evidence_file.write_bytes(
            b"different authorization evidence bytes\n"
        )
        with self.assertRaises(N6PhysicalExecutionError):
            fixture.controller(self.root, driver)
        self.assertEqual(driver.total_request_count, 0)

    def test_materialized_schedule_beats_smaller_authority_before_claim(self) -> None:
        fixture = N6PhysicalFixture(
            self.root,
            last_visible_refresh="2026-08-08T12:03:00+08:00",
            minimum_interval_seconds=120,
            authority_interval_seconds=10,
        )
        driver = self._idle_http_driver()
        with self.assertRaisesRegex(
            N6PhysicalExecutionError, "materialized runtime schedule"
        ):
            fixture.controller(self.root, driver)
        self.assertEqual(driver.total_request_count, 0)
        declaration = fixture.manifest["legacy_formal_manifest"]["action"]["claim"]
        claim = self.root / declaration["workspace_relative_registry"] / declaration["filename"]
        self.assertFalse(claim.exists())

    def test_wrong_exact_token_and_stale_live_validation_are_preclaim(self) -> None:
        fixture = N6PhysicalFixture(self.root)
        driver = self._idle_http_driver()
        controller = fixture.controller(self.root, driver)
        fixture.prepare_browser(controller)
        with self.assertRaisesRegex(N6PhysicalExecutionError, "three exact"):
            controller.arm(
                "wrong-action-token",
                panel_plan_confirmation=required_n6_panel_plan_confirmation(
                    fixture.manifest
                ),
                profile_confirmation=required_n6_profile_confirmation(
                    fixture.manifest
                ),
                token_validated=True,
                same_origin_validated=True,
            )
        self.assertEqual(driver.total_request_count, 0)

        stale_workspace = self.root / "stale-workspace"
        stale_workspace.mkdir()
        stale = fixture.controller(
            stale_workspace,
            driver,
            clock=SequenceClock(
                INITIAL_LIVE_AT,
                "2026-08-08T12:09:31+08:00",
            ),
        )
        fixture.prepare_browser(stale)
        fixture.arm(stale)
        with self.assertRaisesRegex(N6PhysicalExecutionError, "older than 300"):
            stale.enqueue(
                DEFAULT_MAPPINGS,
                token_validated=True,
                same_origin_validated=True,
            )
        self.assertEqual(driver.total_request_count, 0)

        expired_workspace = self.root / "expired-workspace"
        expired_workspace.mkdir()
        with self.assertRaises(N6PhysicalExecutionError):
            fixture.controller(
                expired_workspace,
                driver,
                clock=SequenceClock("2026-08-08T14:00:01+08:00"),
            )
        self.assertEqual(driver.total_request_count, 0)

    def test_claim_directory_fsync_failure_is_zero_post_durable_unknown(self) -> None:
        fixture = N6PhysicalFixture(self.root)
        claim_store = AtomicN6ClaimStore(self.root)
        claim_store.prepare_registry(fixture.manifest["legacy_formal_manifest"])
        driver = self._idle_http_driver()
        controller = fixture.controller(self.root, driver)
        fixture.prepare_browser(controller)
        fixture.arm(controller)

        with mock.patch(
            "host.application.n6_visible_execution.fsync_directory",
            side_effect=OSError("synthetic claim-directory fsync failure"),
        ):
            with self.assertRaises(N6PhysicalPostClaimUnknown):
                controller.enqueue(
                    DEFAULT_MAPPINGS,
                    token_validated=True,
                    same_origin_validated=True,
                )

        self.assertEqual(driver.total_request_count, 0)
        self.assertEqual(
            controller.receipt["legacy_protocol_receipt"]["state"],
            "UNKNOWN_DO_NOT_RETRY",
        )
        self.assertIsNotNone(controller.receipt_durable_commit)
        self.assertTrue(controller.receipt_paths.receipt_output.is_file())
        self.assertTrue(controller.receipt_paths.receipt_commit_output.is_file())
        self.assertFalse(controller.receipt_paths.incident_output.exists())

    def test_receipt_directory_fsync_failure_commits_incident_and_blocks_replay(
        self,
    ) -> None:
        fixture = N6PhysicalFixture(self.root)
        claim_store = AtomicN6ClaimStore(self.root)
        claim_store.prepare_registry(fixture.manifest["legacy_formal_manifest"])
        driver = self._success_http_driver()
        controller = fixture.controller(self.root, driver)
        fixture.prepare_browser(controller)
        fixture.arm(controller)

        from host.application import durable_io

        real_fsync_directory = durable_io.fsync_directory
        calls = 0

        def fail_first_store_directory_fsync(directory: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("synthetic receipt-directory fsync failure")
            real_fsync_directory(directory)

        with mock.patch(
            "host.application.durable_io.fsync_directory",
            side_effect=fail_first_store_directory_fsync,
        ):
            with self.assertRaises(N6PhysicalPostClaimUnknown):
                controller.enqueue(
                    DEFAULT_MAPPINGS,
                    token_validated=True,
                    same_origin_validated=True,
                )

        self.assertEqual(driver.frame_post_request_count, 1)
        self.assertIsNone(controller.receipt_durable_commit)
        self.assertTrue(controller.receipt_paths.receipt_output.is_file())
        self.assertFalse(controller.receipt_paths.receipt_commit_output.exists())
        self.assertTrue(controller.receipt_paths.incident_output.is_file())

        incident = json.loads(
            controller.receipt_paths.incident_output.read_text(encoding="utf-8")
        )
        validated_incident = validate_n6_physical_postclaim_incident(
            incident,
            manifest=fixture.manifest,
            sources=fixture.sources,
            production_files=fixture.production_files,
            static_evidence_files=fixture.static_files,
            receipt_paths=controller.receipt_paths,
            claim_store=AtomicN6ClaimStore(self.root),
        )
        self.assertEqual(validated_incident["state"], "UNKNOWN_DO_NOT_RETRY")

        receipt = controller.receipt
        forged_commit = n6_physical._build_n6_physical_receipt_durable_commit(  # noqa: SLF001
            receipt,
            paths=controller.receipt_paths,
            committed_at=COMPLETED_AT,
        )
        write_new_bytes_durable(
            controller.receipt_paths.receipt_commit_output,
            canonical_json_bytes(forged_commit),
        )
        with self.assertRaisesRegex(
            N6PhysicalExecutionError, "UNKNOWN incident exists"
        ):
            validate_n6_physical_receipt_durable_commit(
                forged_commit,
                receipt=receipt,
                paths=controller.receipt_paths,
            )

    def test_keyboard_interrupt_after_claim_becomes_durable_unknown(self) -> None:
        fixture = N6PhysicalFixture(self.root)
        driver = self._interrupt_after_post_http_driver()
        controller = fixture.controller(self.root, driver)
        fixture.prepare_browser(controller)
        fixture.arm(controller)

        with self.assertRaises(N6PhysicalPostClaimUnknown):
            controller.enqueue(
                DEFAULT_MAPPINGS,
                token_validated=True,
                same_origin_validated=True,
            )

        self.assertEqual(driver.frame_post_request_count, 1)
        self.assertEqual(
            controller.receipt["legacy_protocol_receipt"]["state"],
            "UNKNOWN_DO_NOT_RETRY",
        )
        self.assertIsNotNone(controller.receipt_durable_commit)
        self.assertTrue(controller.receipt_paths.receipt_output.is_file())
        self.assertTrue(controller.receipt_paths.receipt_commit_output.is_file())
        self.assertFalse(controller.receipt_paths.incident_output.exists())

    def test_requester_claim_consumed_exception_after_claim_is_durable_unknown(
        self,
    ) -> None:
        fixture = N6PhysicalFixture(self.root)
        driver = self._claim_consumed_requester_driver()
        controller = fixture.controller(self.root, driver)
        fixture.prepare_browser(controller)
        fixture.arm(controller)

        with self.assertRaises(N6PhysicalPostClaimUnknown):
            controller.enqueue(
                DEFAULT_MAPPINGS,
                token_validated=True,
                same_origin_validated=True,
            )

        self.assertEqual(driver.total_request_count, 1)
        self.assertEqual(driver.frame_post_request_count, 0)
        self.assertEqual(
            controller.receipt["legacy_protocol_receipt"]["state"],
            "UNKNOWN_DO_NOT_RETRY",
        )
        self.assertIsNotNone(controller.receipt_durable_commit)

    def test_one_post_duplicate_replay_and_deep_final_chain(self) -> None:
        fixture = N6PhysicalFixture(self.root)
        driver = self._success_http_driver()
        controller = fixture.controller(self.root, driver)
        fixture.prepare_browser(controller)
        fixture.arm(controller)
        result = controller.enqueue(
            DEFAULT_MAPPINGS,
            token_validated=True,
            same_origin_validated=True,
        )
        self.assertTrue(result["accepted"])
        self.assertEqual(driver.frame_post_request_count, 1)
        receipt = controller.receipt
        assert receipt is not None
        validate_n6_physical_receipt(
            receipt,
            manifest=fixture.manifest,
            sources=fixture.sources,
            production_files=fixture.production_files,
            static_evidence_files=fixture.static_files,
            runtime_evidence_files=fixture.runtime_files,
            evaluated_at=COMPLETED_AT,
        )
        with self.assertRaises(N6PhysicalExecutionError):
            controller.enqueue(
                DEFAULT_MAPPINGS,
                token_validated=True,
                same_origin_validated=True,
            )
        replay_driver = self._idle_http_driver()
        replay = fixture.controller(
            self.root,
            replay_driver,
            clock=SequenceClock(
                "2026-08-08T12:04:33+08:00",
                "2026-08-08T12:04:34+08:00",
                "2026-08-08T12:04:35+08:00",
            ),
            receipt_tag="replay-physical-receipt",
        )
        fixture.prepare_browser(replay)
        fixture.arm(replay)
        with self.assertRaises(N6ClaimConsumed):
            replay.enqueue(
                DEFAULT_MAPPINGS,
                token_validated=True,
                same_origin_validated=True,
            )
        self.assertEqual(replay_driver.total_request_count, 0)

        legacy_manifest = fixture.manifest["legacy_formal_manifest"]
        legacy_receipt = receipt["legacy_protocol_receipt"]
        manual = seal_n6_manual_observation(
            {
                "schema_version": 1,
                "kind": MANUAL_OBSERVATION_KIND,
                "formal_manifest_canonical_sha256": legacy_manifest["integrity"][
                    "canonical_sha256"
                ],
                "protocol_receipt_canonical_sha256": legacy_receipt["integrity"][
                    "canonical_sha256"
                ],
                "action_identity_sha256": legacy_manifest["action"][
                    "action_identity_sha256"
                ],
                "attempt_id": legacy_receipt["attempt_id"],
                "observed_at": "2026-08-08T12:04:40+08:00",
                "observer_id": "n6-physical-observer",
                "full_panel_visual_matches_preview": True,
                "map_fidelity_pass": True,
                "orientation_seam_and_ghosting_normal": True,
                "supply_cv_current_normal": True,
                "post_refresh_current_normal": True,
                "temperature_normal": True,
                "esp32_unexpected_restart": False,
                "j2_state_after_observation": "on",
                "manual_evidence_sha256": "a" * 64,
                "notes": "synthetic offline structural test only",
            },
            manifest=legacy_manifest,
            protocol_receipt=legacy_receipt,
        )
        finalized = finalize_n6_physical_manual_observation(
            fixture.manifest,
            receipt,
            manual,
            receipt_durable_commit=controller.receipt_durable_commit,
            receipt_paths=controller.receipt_paths,
            claim_store=AtomicN6ClaimStore(self.root),
            finalized_at="2026-08-08T12:04:41+08:00",
        )
        validate_n6_physical_finalized_bundle(
            finalized,
            manifest=fixture.manifest,
            sources=fixture.sources,
            production_files=fixture.production_files,
            static_evidence_files=fixture.static_files,
            runtime_evidence_files=fixture.runtime_files,
            receipt_paths=controller.receipt_paths,
            claim_store=AtomicN6ClaimStore(self.root),
        )
        tampered = deepcopy(finalized)
        tampered["required_token_sha256"]["action_authorization"] = "0" * 64
        with self.assertRaises(N6PhysicalExecutionError):
            validate_n6_physical_finalized_bundle(
                tampered,
                manifest=fixture.manifest,
                sources=fixture.sources,
                production_files=fixture.production_files,
                static_evidence_files=fixture.static_files,
                runtime_evidence_files=fixture.runtime_files,
                receipt_paths=controller.receipt_paths,
                claim_store=AtomicN6ClaimStore(self.root),
            )


class N6LegacySurfaceBlockTests(unittest.TestCase):
    def test_public_legacy_enqueue_is_hard_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            controller = legacy_fixture.formal_manifest()
            driver = RecordingDriver(legacy_fixture.success_protocol_result())
            from host.application.n6_visible_execution import N6BrowserExecutionController

            legacy_controller = N6BrowserExecutionController(
                controller,
                authorization=legacy_fixture.authorization(),
                runtime_observation=legacy_fixture.runtime_observation(),
                claim_store=AtomicN6ClaimStore(directory),
                protocol_driver=driver,
                attempt_id="legacy-public-block-test",
            )
            with self.assertRaisesRegex(N6VisibleExecutionError, "legacy N6"):
                legacy_controller.enqueue(
                    DEFAULT_MAPPINGS,
                    token_validated=True,
                    same_origin_validated=True,
                )
            self.assertEqual(driver.calls, 0)


if __name__ == "__main__":
    unittest.main()
