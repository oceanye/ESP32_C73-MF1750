"""Cached, fully replayable N5 physical palette evidence for N6 tests."""

from __future__ import annotations

from dataclasses import dataclass
import contextlib
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping

from host.extended_color import aggregation, execution, n5_rc2g_protocol, spectral
from host.extended_color.spectral import (
    REFLECTANCE_KIND,
    integrate_reflectance,
    seal_reflectance_record,
    spectral_report_file_sha256,
)
from host.visible_refresh_campaign import canonical_json_bytes
from tests.n5_execution_fixture import dependency_closure
from tests.test_extended_color_aggregation import (
    _qualification,
    _reflectance,
    _structural_table,
)
from tests.test_g1_s1_rc2g_map_baseline_once import (
    ScriptedRequester,
    TickClock,
    _responses as map_responses,
)
from tests.test_g1_s1_rc2g_quality_refresh_once import (
    _responses as quality_responses,
)
from tools import mf1750_n5_fixed_execution as fixed
from tools import mf1750_n5_measurement_campaign as source
from tools import mf1750_n5_physical_campaign as physical_campaign
from tools import mf1750_n5_physical_execution as physical
from host.visible_refresh_campaign import production_profile as production


INTERVAL_SECONDS = 180.0
COOLDOWN_SECONDS = 240.0
NAMESPACE = "n6-cross-stage-v1"
_FROZEN_D65_WHITE = (95.047, 100.0, 108.883)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> Path:
    path.write_bytes(canonical_json_bytes(value))
    return path


def _stable_structural_table() -> Mapping[str, Any]:
    """Return structural rows whose white point also matches frozen D65."""

    with _structural_table() as original:
        rows = json.loads(canonical_json_bytes(original["rows"]).decode("utf-8"))
        current = original["white_point_xyz_Y100"]
        x_scale = _FROZEN_D65_WHITE[0] / current[0]
        z_scale = _FROZEN_D65_WHITE[2] / current[2]
        for row in rows:
            row["x_bar"] *= x_scale
            row["z_bar"] *= z_scale
        math_result = spectral.integrate_numeric_grid_unqualified(
            wavelengths_nm=[row["wavelength_nm"] for row in rows],
            illuminant_spd=[row["d65_spd"] for row in rows],
            x_bar=[row["x_bar"] for row in rows],
            y_bar=[row["y_bar"] for row in rows],
            z_bar=[row["z_bar"] for row in rows],
            reflectance=[1.0] * len(rows),
        )
        unsigned = {
            key: value
            for key, value in original.items()
            if key != "integrity"
        }
        unsigned["rows"] = rows
        unsigned["rows_canonical_sha256"] = spectral._sha256(rows)  # noqa: SLF001
        unsigned["white_point_xyz_Y100"] = math_result["white_xyz"]
        table = {
            **unsigned,
            "integrity": spectral._integrity(  # noqa: SLF001
                unsigned, spectral.TABLE_HASH_SCOPE
            ),
        }
    spectral.validate_authoritative_standard_table(table)
    return table


class _SequenceClock:
    def __init__(self, *values: str) -> None:
        self._values = list(values)

    def __call__(self) -> str:
        if not self._values:
            raise AssertionError("N5 fixture wall clock was read too many times")
        return self._values.pop(0)


@dataclass(frozen=True)
class PhysicalPaletteFixture:
    context: physical.N5PhysicalContext
    observations: tuple[Mapping[str, Any], ...]
    observation_files: tuple[Path, ...]
    standard_table: Mapping[str, Any]
    standard_table_file: Path
    instrument_qualification: Mapping[str, Any]
    instrument_qualification_file: Path
    aggregate_envelope: Mapping[str, Any]
    aggregate_file: Path
    inner_aggregate: Mapping[str, Any]
    finalized_bundle: Mapping[str, Any]
    finalized_bundle_file: Path
    result_dirs: tuple[Path, ...]
    profile_reviewer_key_file: Path


_CACHE: dict[str, tuple[tempfile.TemporaryDirectory[str], PhysicalPaletteFixture]] = {}


def cached_physical_palette_fixture(
    *,
    panel: Mapping[str, Any],
    firmware: Mapping[str, Any],
    firmware_bytes: bytes,
) -> PhysicalPaletteFixture:
    key = hashlib.sha256(
        canonical_json_bytes(
            {
                "panel": panel,
                "firmware": firmware,
                "firmware_bytes_sha256": hashlib.sha256(firmware_bytes).hexdigest(),
            }
        )
    ).hexdigest()
    cached = _CACHE.get(key)
    if cached is not None:
        return cached[1]
    temporary: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
    fixture = _build_fixture(
        Path(temporary.name),
        panel=panel,
        firmware=firmware,
        firmware_bytes=firmware_bytes,
    )
    _CACHE[key] = (temporary, fixture)
    return fixture


def _compile_context(
    root: Path,
    *,
    panel: Mapping[str, Any],
    firmware: Mapping[str, Any],
    firmware_bytes: bytes,
    table: Mapping[str, Any],
    qualification: Mapping[str, Any],
) -> physical.N5PhysicalContext:
    cold = source.reviewed_panel_cold_profile(
        minimum_panel_power_off_seconds=60,
        review_artifact_sha256="1" * 64,
    )
    recovery = source.build_reviewed_transition_recovery_profile(
        panel=panel,
        firmware=firmware,
        waveform_id="wf-n5-n6-cross-stage-v1",
        waveform_sha256="2" * 64,
        qualification_artifact_sha256="3" * 64,
        reviewer_id="n5-n6-cross-stage-science-reviewer",
        reviewed_at="2026-08-07T20:00:00Z",
        review_artifact_sha256="4" * 64,
        supplier_limit_profile_sha256="5" * 64,
        usage_limit_contract_sha256="6" * 64,
        temperature_chain_sha256="7" * 64,
    )
    profile = source.seal_compile_profile(
        {
            "schema_version": 1,
            "kind": source.COMPILE_PROFILE_KIND,
            "panel": dict(panel),
            "firmware": dict(firmware),
            "formal_palette_cold_profile": cold,
            "formal_transition_recovery_profile": recovery,
            "formal_transition_power_profile": cold,
            "waveform_id": "wf-n5-n6-cross-stage-v1",
            "waveform_sha256": "2" * 64,
            "temperature_c": 23.0,
            "relative_humidity_percent": 45.0,
            "environment_record_sha256": "8" * 64,
            "standard_table_canonical_sha256": table["integrity"][
                "canonical_sha256"
            ],
            "instrument_qualification_canonical_sha256": qualification[
                "integrity"
            ]["canonical_sha256"],
            "pixel_pitch_review_artifact_sha256": "b" * 64,
            "roi_aperture_fit_review_artifact_sha256": "c" * 64,
            "orientation_bias_max_delta_e00": 10.0,
            "u95_max_delta_e00": 10.0,
            "acceptance_span_delta_e00": 10.0,
            "acceptance_review_artifact_sha256": "d" * 64,
            "acquisition_feasibility_review_artifact_sha256": "e" * 64,
        }
    )
    profile_bytes = canonical_json_bytes(profile)
    manifest = source.compile_manifest_from_profile(profile)
    manifest_bytes = canonical_json_bytes(manifest)
    anchor = manifest["shared_p0"]
    anchor_bytes = canonical_json_bytes(anchor)
    science_evidence = b"N5 to N6 physical science review evidence\n"
    science_key = b"n5-n6-cross-stage-static-review-key-v1"
    approval = physical_campaign.create_static_science_review_approval(
        reviewer_id="n5-n6-cross-stage-static-reviewer",
        reviewed_at="2026-08-07T21:00:00Z",
        science_review_evidence=science_evidence,
        compile_profile=profile,
        compile_profile_bytes=profile_bytes,
        source_manifest=manifest,
        source_manifest_bytes=manifest_bytes,
        physical_anchor=anchor,
        physical_anchor_bytes=anchor_bytes,
        firmware_binary=firmware_bytes,
        minimum_interval_seconds=INTERVAL_SECONDS,
        planned_cooldown_seconds=COOLDOWN_SECONDS,
        reviewer_key=science_key,
    )
    inputs = physical_campaign.N5PhysicalCampaignInputs(
        compile_profile=profile,
        compile_profile_bytes=profile_bytes,
        source_manifest=manifest,
        source_manifest_bytes=manifest_bytes,
        physical_anchor=anchor,
        physical_anchor_bytes=anchor_bytes,
        firmware_binary=firmware_bytes,
        science_review_evidence=science_evidence,
        science_review_approval=approval,
        science_review_approval_bytes=canonical_json_bytes(approval),
        reviewer_key=science_key,
    )
    plan = physical_campaign.compile_n5_physical_plan(
        inputs,
        namespace=NAMESPACE,
        minimum_interval_seconds=INTERVAL_SECONDS,
        planned_cooldown_seconds=COOLDOWN_SECONDS,
    )
    plan_file = _write_json(root / "N5-PRODUCTION-PHYSICAL-PLAN.json", plan)
    return physical.N5PhysicalContext(
        plan=plan,
        plan_bytes=plan_file.read_bytes(),
        inputs=inputs,
        namespace=NAMESPACE,
        minimum_interval_seconds=INTERVAL_SECONDS,
        planned_cooldown_seconds=COOLDOWN_SECONDS,
    )


def _policy(
    context: physical.N5PhysicalContext,
    *,
    index: int,
    evaluated: datetime,
) -> dict[str, Any]:
    limits = {
        "maximum_campaign_visible_refreshes": 100,
        "maximum_session_visible_refreshes": 100,
        "maximum_consecutive_visible_refreshes": 100,
        "minimum_interval_seconds": 60,
        "minimum_cooldown_seconds": 60,
        "minimum_start_temperature_c": 0,
        "maximum_start_temperature_c": 50,
        "maximum_post_refresh_temperature_c": 50,
    }
    temperature_fields = {
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
        "issuer": "n5-n6-cross-stage-process-owner",
        "policy_id": f"n5-n6-cross-stage-policy-{index:02d}",
        "issued_at": _timestamp(evaluated - timedelta(days=1)),
        "panel_model": context.plan["execution_contract"]["p0_campaign"][
            "panel"
        ]["model"],
        "maximum_usage_snapshot_age_seconds": 7200,
        "limits": limits,
        "validity": {
            "valid_from": _timestamp(evaluated - timedelta(seconds=10)),
            "expires_at": _timestamp(evaluated + timedelta(days=1)),
        },
        "field_provenance": {
            field: {
                "classification": (
                    production.EXACT_SUPPLIER_DOCUMENT_PROVENANCE
                    if field in temperature_fields
                    else production.OPERATOR_SELECTED_PROCESS_GATE_PROVENANCE
                ),
                "source_document_sha256": (
                    production.MF1750_A1_SOURCE_DOCUMENT_SHA256
                ),
            }
            for field in limits
        },
    }


def _production_files(
    root: Path,
    context: physical.N5PhysicalContext,
    *,
    index: int,
    action_key: str,
    evaluated: datetime,
    last_completed_at: str | None,
    firmware_file: Path,
    campaign_file: Path,
    profile_key_file: Path,
) -> tuple[physical.N5ProductionFiles, production.ValidatedProductionProfile]:
    authority_file = _write_json(
        root / f"limit-authority-{index:02d}.json",
        _policy(context, index=index, evaluated=evaluated),
    )
    campaign = context.plan["execution_contract"]["p0_campaign"]
    usage_file = _write_json(
        root / f"usage-{index:02d}.json",
        {
            "schema_version": 1,
            "kind": production.USAGE_EVIDENCE_KIND,
            "evidence_id": f"n5-n6-cross-stage-usage-{index:02d}",
            "campaign_canonical_sha256": campaign["integrity"][
                "canonical_sha256"
            ],
            "panel": campaign["panel"],
            "firmware": campaign["firmware"],
            "usage": {
                "cumulative_visible_refresh_count": index + 1,
                "session_visible_refresh_count": 1,
                "consecutive_visible_refresh_count": 1,
                "last_visible_refresh_completed_at": _timestamp(
                    evaluated - timedelta(minutes=10)
                )
                if last_completed_at is None
                else last_completed_at,
                "snapshot_at": _timestamp(evaluated - timedelta(seconds=30)),
            },
        },
    )
    draft = production.compile_production_draft_from_files(
        campaign_file=campaign_file,
        firmware_binary_file=firmware_file,
        supplier_limits_file=authority_file,
        usage_evidence_file=usage_file,
        profile_id=f"n5-n6-cross-stage-profile-{index:02d}",
        profile_version="1.0.0",
    )
    draft_file = _write_json(root / f"profile-draft-{index:02d}.json", draft)
    approval = production.create_production_approval(
        draft_profile_file=draft_file,
        campaign_file=campaign_file,
        firmware_binary_file=firmware_file,
        supplier_limits_file=authority_file,
        usage_evidence_file=usage_file,
        reviewer_id="n5-n6-cross-stage-profile-reviewer",
        reviewed_at=_timestamp(evaluated - timedelta(seconds=15)),
        reviewer_key_file=profile_key_file,
    )
    profile_file = root / f"profile-{index:02d}.json"
    review_file = root / f"profile-review-{index:02d}.json"
    production.publish_approval_bundle(
        approval,
        review_artifact_output=review_file,
        profile_output=profile_file,
    )
    files = physical.N5ProductionFiles(
        profile=profile_file,
        physical_campaign=campaign_file,
        firmware_binary=firmware_file,
        limit_authority=authority_file,
        usage_evidence=usage_file,
        review_artifact=review_file,
        reviewer_key=profile_key_file,
    )
    validated = physical.load_n5_physical_production_profile(
        context,
        action_key,
        files,
        evaluated_at=_timestamp(evaluated),
    )
    return files, validated


def _build_observation_inputs(
    plan: Mapping[str, Any],
    table: Mapping[str, Any],
    qualification: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    wavelengths = [row["wavelength_nm"] for row in table["rows"]]
    payloads: list[dict[str, Any]] = []
    bindings: dict[str, list[dict[str, Any]]] = {}
    for index, slot in enumerate(plan["expected_slots"]):
        measurement_id = f"n5-n6-cross-stage-palette-{index:03d}"
        reflectance = seal_reflectance_record(
            {
                "schema_version": 1,
                "kind": REFLECTANCE_KIND,
                "measurement_id": measurement_id,
                "grid": table["grid"],
                "reflectance": _reflectance(slot["code"], wavelengths),
                "raw_spectrum_artifact_sha256": _hash_text(f"raw-{index}"),
                "measurement_record_sha256": _hash_text(
                    f"measurement-{index}"
                ),
                "instrument_qualification_sha256": qualification["integrity"][
                    "canonical_sha256"
                ],
            }
        )
        report = integrate_reflectance(table, reflectance)
        run_key = f"{slot['orientation']}-{slot['formal_run']}"
        source_run_sha = _hash_text(f"source-run-{run_key}")
        asset_sha = _hash_text(f"asset-{run_key}")
        report_sha = spectral_report_file_sha256(report)
        target_sha = str(slot["target_action_identity_sha256"])
        bindings.setdefault(target_sha, []).append(
            {
                "slot_id": slot["slot_id"],
                "measurement_phase": "palette",
                "source_run_sha256": source_run_sha,
                "asset_manifest_sha256": asset_sha,
                "measurement_record_sha256": reflectance[
                    "measurement_record_sha256"
                ],
                "raw_spectrum_artifact_sha256": reflectance[
                    "raw_spectrum_artifact_sha256"
                ],
                "spectral_report_file_sha256": report_sha,
                "metrics_sha256": None,
            }
        )
        payloads.append(
            {
                "schema_version": 1,
                "kind": aggregation.PALETTE_OBSERVATION_KIND,
                "plan_canonical_sha256": plan["integrity"][
                    "canonical_sha256"
                ],
                "slot_id": slot["slot_id"],
                "context": plan["context"],
                "captured_at": "2026-08-08T12:00:00Z",
                "seconds_after_pof_busy_high": 55.0
                + slot["measurement_order"],
                "source_run_sha256": source_run_sha,
                "asset_manifest_sha256": asset_sha,
                "authorization_id": None,
                "primer_action_identity_sha256": slot[
                    "primer_action_identity_sha256"
                ],
                "target_action_identity_sha256": target_sha,
                "primer_result_file_sha256": None,
                "target_result_file_sha256": None,
                "reflectance_record": reflectance,
                "spectral_report": report,
                "spectral_report_file_sha256": report_sha,
            }
        )
    return payloads, bindings


def _ordered_bindings(
    snapshot: execution.ActionSnapshot,
    by_action: Mapping[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    supplied = {
        item["slot_id"]: item
        for item in by_action.get(
            str(snapshot.action["action_identity_sha256"]), []
        )
    }
    return [supplied[slot["slot_id"]] for slot in snapshot.measurement_slots]


def _session_start(
    snapshot: execution.ActionSnapshot, observed: datetime
) -> Mapping[str, Any]:
    cold = snapshot.session["power_mode"] == "panel_cold_cycle"
    return execution.seal_session_start(
        {
            "schema_version": 1,
            "kind": execution.SESSION_START_KIND,
            "session_id": snapshot.session["session_id"],
            "observed_at": _timestamp(observed),
            "power_mode": snapshot.session["power_mode"],
            "j2_initially_off": cold,
            "measured_panel_power_off_seconds": (
                float(snapshot.session["minimum_panel_power_off_seconds"])
                if cold
                else None
            ),
            "controller_fresh_boot_observed": cold,
            "j2_on_before_first_action": True,
            "supply_cv_current_normal": True,
            "temperature_normal": True,
            "physical_cutoff_available": True,
            "observation_artifact_sha256": _hash_text(
                f"session-{snapshot.session['session_id']}"
            ),
        },
        snapshot=snapshot,
    )


def _authorization(
    context: physical.N5PhysicalContext,
    snapshot: execution.ActionSnapshot,
    entry: Mapping[str, Any],
    profile: production.ValidatedProductionProfile,
    session_start: Mapping[str, Any],
    evaluated: datetime,
) -> tuple[Mapping[str, Any], str, str, str]:
    action_token = physical.required_action_token(context, snapshot.key)
    panel_token = physical.required_panel_plan_token(context, snapshot.key)
    profile_token = physical.required_profile_token(profile)
    confirmation = physical.authorization_confirmation_sha256(
        action_token=action_token,
        panel_plan_token=panel_token,
        profile_token=profile_token,
    )
    authorization = execution._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": execution.AUTHORIZATION_KIND,
            "authorization_id": f"N5-N6-AUTH-{entry['order']:03d}",
            "action_identity_sha256": entry["action_identity_sha256"],
            "execution_contract_canonical_sha256": context.plan[
                "execution_contract"
            ]["integrity"]["canonical_sha256"],
            "session_start_file_sha256": execution._sha256(session_start),
            "issued_at": _timestamp(evaluated),
            "expires_at": _timestamp(evaluated + timedelta(hours=1)),
            "operator_id": "n5-n6-cross-stage-operator",
            "authorization_artifact_sha256": _hash_text(
                f"authorization-{entry['order']}"
            ),
            "confirmation_sha256": confirmation,
            "maximum_post_requests": 1,
            "automatic_advance_authorized": False,
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
        }
    )
    return authorization, action_token, panel_token, profile_token


def _scripted_driver(
    contract: Mapping[str, Any],
    snapshot: execution.ActionSnapshot,
    frame: bytes,
    prior_item: Mapping[str, Any] | None,
) -> tuple[Any, Any]:
    candidate = n5_rc2g_protocol._candidate_snapshot(snapshot, frame)  # noqa: SLF001
    first_in_session, previous_session_sha = n5_rc2g_protocol._session_position(  # noqa: SLF001
        snapshot
    )
    if first_in_session:
        run = n5_rc2g_protocol._fresh_run_contract(candidate)  # noqa: SLF001
        responses = quality_responses(frame, run)
        fresh = map_responses()
        responses["/api/job"][0] = fresh["/api/job"][0]
        responses["/api/diagnostic/report"][0] = fresh[
            "/api/diagnostic/report"
        ][0]
    else:
        if prior_item is None or previous_session_sha is None:
            raise AssertionError("same-session physical action lost its predecessor")
        evidence = prior_item["protocol_evidence"]["device_evidence"]
        run = n5_rc2g_protocol._completed_run_contract(  # noqa: SLF001
            candidate,
            evidence["target_job_raw"],
            evidence["target_diagnostic_raw"],
            prior_frame_sha256=evidence["completed_action"]["frame_sha256"],
            prior_scope="exact preceding finalized N5 strict device evidence",
        )
        responses = quality_responses(frame, run)
        responses["/api/job"][0] = (
            200,
            json.dumps(evidence["target_job_raw"]),
        )
        responses["/api/diagnostic/report"][0] = (
            200,
            json.dumps(evidence["target_diagnostic_raw"]),
        )
    scripted = ScriptedRequester(responses)
    transport = n5_rc2g_protocol.make_http_transport(
        "http://fixture-device", requester=scripted
    )
    driver = n5_rc2g_protocol.make_protocol_driver(
        contract,
        snapshot.key,
        prior_item,
        base_url="http://fixture-device",
        sleeper=lambda _seconds: None,
        clock=TickClock(),
    )
    return transport, driver


def _build_fixture(
    root: Path,
    *,
    panel: Mapping[str, Any],
    firmware: Mapping[str, Any],
    firmware_bytes: bytes,
) -> PhysicalPaletteFixture:
    with contextlib.nullcontext(_stable_structural_table()) as table:
        qualification = _qualification(table)
        standard_table_file = _write_json(root / "standard-table.json", table)
        instrument_qualification_file = _write_json(
            root / "instrument-qualification.json", qualification
        )
        context = _compile_context(
            root,
            panel=panel,
            firmware=firmware,
            firmware_bytes=firmware_bytes,
            table=table,
            qualification=qualification,
        )
        contract = context.plan["execution_contract"]
        palette_plan = context.plan["runtime_manifest"]["formal_palette_plan"]
        observation_payloads, measurement_bindings = _build_observation_inputs(
            palette_plan, table, qualification
        )
        required = {
            str(slot[field])
            for slot in palette_plan["expected_slots"]
            for field in (
                "primer_action_identity_sha256",
                "target_action_identity_sha256",
            )
        }
        included = set(dependency_closure(contract, sorted(required)))
        campaign_file = _write_json(
            root / "physical-campaign.json", contract["p0_campaign"]
        )
        firmware_file = root / "firmware.bin"
        firmware_file.write_bytes(firmware_bytes)
        profile_key_file = root / "profile-reviewer.key"
        profile_key_file.write_bytes(
            b"n5-n6-cross-stage-profile-reviewer-key-v1"
        )
        claim_root = root / "claims"
        base = datetime(2026, 8, 8, tzinfo=timezone.utc)
        prior_item: Mapping[str, Any] | None = None
        prior_result_dir: Path | None = None
        result_dirs: list[Path] = []
        session_starts: dict[str, Mapping[str, Any]] = {}
        for sequence, entry in enumerate(contract["actions"]):
            if entry["action_identity_sha256"] not in included:
                continue
            snapshot = execution.load_action_snapshot(contract, entry["action_key"])
            evaluated = base + timedelta(minutes=10 * (sequence + 1))
            files, validated_profile = _production_files(
                root,
                context,
                index=sequence,
                action_key=snapshot.key,
                evaluated=evaluated,
                last_completed_at=(
                    None
                    if prior_item is None
                    else str(prior_item["result"]["completed_at"])
                ),
                firmware_file=firmware_file,
                campaign_file=campaign_file,
                profile_key_file=profile_key_file,
            )
            session_start = session_starts.setdefault(
                snapshot.session["session_id"],
                _session_start(snapshot, evaluated - timedelta(minutes=1)),
            )
            authorization, action_token, panel_token, profile_token = _authorization(
                context,
                snapshot,
                entry,
                validated_profile,
                session_start,
                evaluated,
            )
            frame = fixed.load_action_frame(contract, snapshot.key)
            transport, driver = _scripted_driver(
                contract, snapshot, frame, prior_item
            )
            result_dir = root / f"result-{entry['order']:03d}"
            physical.run_n5_physical_action_once(
                context,
                snapshot.key,
                production_files=files,
                authorization=authorization,
                session_start=session_start,
                prior_bundle=prior_item,
                prior_result_dir=prior_result_dir,
                result_dir=result_dir,
                claim_root=claim_root,
                base_url="http://fixture-device",
                action_token=action_token,
                panel_plan_token=panel_token,
                profile_token=profile_token,
                start_temperature_c=23.0,
                confirm_supply_cv_current_normal=True,
                confirm_j2_on=True,
                confirm_physical_cutoff_available=True,
                wall_clock=_SequenceClock(
                    _timestamp(evaluated),
                    _timestamp(evaluated + timedelta(seconds=1)),
                ),
                transport=transport,
                protocol_driver=driver,
            )
            receipt = json.loads(
                (result_dir / fixed.RESULT_RECEIPT_FILE).read_text(
                    encoding="utf-8"
                )
            )
            manual = {
                "schema_version": 1,
                "kind": execution.MANUAL_OBSERVATION_KIND,
                "execution_contract_canonical_sha256": contract["integrity"][
                    "canonical_sha256"
                ],
                "attempt_id": receipt["claim"]["attempt_id"],
                "action_key": snapshot.key,
                "action_identity_sha256": entry["action_identity_sha256"],
                "protocol_evidence_file_sha256": receipt[
                    "protocol_evidence_file_sha256"
                ],
                "observed_at": _timestamp(evaluated + timedelta(minutes=1)),
                "source_observation_artifact_sha256": _hash_text(
                    f"manual-{entry['order']}"
                ),
                "visual_pass": True,
                "electrical_pass": True,
                "thermal_pass": True,
                "measurement_pass": True,
                "continuity": execution.expected_continuity(
                    contract, snapshot.key
                ),
                "measurement_bindings": _ordered_bindings(
                    snapshot, measurement_bindings
                ),
                "notes": "N5 to N6 physical cross-stage fixture",
            }
            physical.finalize_n5_physical_action(
                context,
                result_dir,
                manual_observation_payload=manual,
                claim_root=claim_root,
                profile_reviewer_key_file=profile_key_file,
                wall_clock=_SequenceClock(
                    _timestamp(evaluated + timedelta(minutes=1, seconds=1))
                ),
            )
            prior_item = json.loads(
                (result_dir / fixed.RESULT_ACTION_ITEM_FILE).read_text(
                    encoding="utf-8"
                )
            )
            prior_result_dir = result_dir
            result_dirs.append(result_dir)

        bundle_file = root / "physical-finalized-bundle.json"
        physical.build_n5_physical_session_bundle(
            context,
            result_dirs=result_dirs,
            session_starts=list(session_starts.values()),
            finalized_at=_timestamp(base + timedelta(hours=8)),
            j2_cut_session_ids=[],
            profile_reviewer_key_file=profile_key_file,
            output_file=bundle_file,
        )
        bundle = json.loads(bundle_file.read_text(encoding="utf-8"))
        summary = execution.validate_finalized_bundle(contract, bundle)
        observations = []
        for payload in observation_payloads:
            primer = summary["actions_by_sha"][
                payload["primer_action_identity_sha256"]
            ]
            target = summary["actions_by_sha"][
                payload["target_action_identity_sha256"]
            ]
            payload.update(
                {
                    "execution_contract_canonical_sha256": contract["integrity"][
                        "canonical_sha256"
                    ],
                    "finalized_bundle_canonical_sha256": bundle["integrity"][
                        "canonical_sha256"
                    ],
                    "authorization_id": target["authorization_id"],
                    "primer_result_file_sha256": primer[
                        "result_file_sha256"
                    ],
                    "target_result_file_sha256": target[
                        "result_file_sha256"
                    ],
                }
            )
            observations.append(
                aggregation.seal_palette_observation(
                    payload,
                    plan=palette_plan,
                    standard_table=table,
                    instrument_qualification=qualification,
                )
            )
        envelope = physical.aggregate_n5_physical_palette(
            context,
            observations,
            standard_table=table,
            instrument_qualification=qualification,
            finalized_bundle=bundle,
            result_dirs=result_dirs,
            profile_reviewer_key_file=profile_key_file,
        )
        observation_files = tuple(
            _write_json(root / f"palette-observation-{index:03d}.json", value)
            for index, value in enumerate(observations)
        )
        aggregate_file = _write_json(root / "physical-palette-aggregate.json", envelope)
        return PhysicalPaletteFixture(
            context=context,
            observations=tuple(observations),
            observation_files=observation_files,
            standard_table=table,
            standard_table_file=standard_table_file,
            instrument_qualification=qualification,
            instrument_qualification_file=instrument_qualification_file,
            aggregate_envelope=envelope,
            aggregate_file=aggregate_file,
            inner_aggregate=envelope["aggregate"],
            finalized_bundle=bundle,
            finalized_bundle_file=bundle_file,
            result_dirs=tuple(result_dirs),
            profile_reviewer_key_file=profile_key_file,
        )


__all__ = ["PhysicalPaletteFixture", "cached_physical_palette_fixture"]
