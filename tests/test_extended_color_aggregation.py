from __future__ import annotations

import contextlib
import copy
import hashlib
import math
import unittest
from unittest.mock import patch

import host.extended_color.aggregation as aggregation
import host.extended_color.execution as execution
import host.extended_color.spectral as spectral
from host.extended_color.aggregation import (
    INSTRUMENT_KIND,
    PALETTE_OBSERVATION_KIND,
    TRANSITION_OBSERVATION_KIND,
    MeasurementAggregationError,
    aggregate_measured_palette,
    aggregate_production_measured_palette,
    aggregate_transition_profile,
    seal_instrument_qualification,
    seal_palette_observation,
    seal_transition_observation,
    summarize_numeric,
    validate_instrument_qualification,
    validate_palette_aggregate,
    validate_transition_aggregate,
)
from host.extended_color.spectral import (
    AUTHORITY_KIND,
    REFLECTANCE_KIND,
    compile_authoritative_standard_table,
    integrate_numeric_grid_unqualified,
    integrate_reflectance,
    seal_authority_manifest,
    seal_reflectance_record,
    spectral_report_file_sha256,
)
from tools.mf1750_n5_measurement_campaign import (
    DEFAULT_FIRMWARE,
    DEFAULT_PANEL,
    build_reviewed_transition_recovery_profile,
    compile_campaign_manifest,
    reviewed_panel_cold_profile,
)
from tests.n5_execution_fixture import build_pass_bundle


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _bound_panel() -> dict[str, str]:
    return {**DEFAULT_PANEL, "serial": "PANEL-N5-AGG-001"}


@contextlib.contextmanager
def _structural_table():
    """Synthetic structural rows stay in this test and are never a CIE asset."""

    wavelengths = list(range(360, 831, 5))
    xbar = [0.01 + math.exp(-0.5 * ((value - 610) / 45) ** 2) for value in wavelengths]
    ybar = [0.01 + math.exp(-0.5 * ((value - 545) / 40) ** 2) for value in wavelengths]
    zbar = [
        0.01 + 1.4 * math.exp(-0.5 * ((value - 450) / 32) ** 2)
        for value in wavelengths
    ]
    d65 = ("\n".join(f"{value},1" for value in wavelengths) + "\n").encode()
    cmf = (
        "\n".join(
            f"{value},{x:.17g},{y:.17g},{z:.17g}"
            for value, x, y, z in zip(wavelengths, xbar, ybar, zbar)
        )
        + "\n"
    ).encode()
    authority = seal_authority_manifest(
        {
            "schema_version": 1,
            "kind": AUTHORITY_KIND,
            "output_grid": {
                "wavelength_unit": "nm",
                "start_nm": 360,
                "end_nm": 830,
                "interval_nm": 5,
                "sample_count": 95,
            },
            "sources": [
                {
                    "role": "d65_spd",
                    "publisher": "CIE",
                    "authority_type": "standards-body-primary-table",
                    "dataset_identifier": "STRUCTURAL-TEST-ONLY",
                    "source_uri": "https://files.cie.co.at/structural-test-d65.csv",
                    "artifact_sha256": hashlib.sha256(d65).hexdigest(),
                    "csv": {
                        "encoding": "utf-8",
                        "delimiter": ",",
                        "header_rows": 0,
                        "column_order": ["wavelength_nm", "relative_spd"],
                    },
                },
                {
                    "role": "cie_1931_2deg_cmf",
                    "publisher": "CIE",
                    "authority_type": "standards-body-primary-table",
                    "dataset_identifier": "STRUCTURAL-TEST-ONLY",
                    "source_uri": "https://files.cie.co.at/structural-test-cmf.csv",
                    "artifact_sha256": hashlib.sha256(cmf).hexdigest(),
                    "csv": {
                        "encoding": "utf-8",
                        "delimiter": ",",
                        "header_rows": 0,
                        "column_order": [
                            "wavelength_nm",
                            "x_bar",
                            "y_bar",
                            "z_bar",
                        ],
                    },
                },
            ],
            "review": {
                "approved": True,
                "reviewer_id": "structural-test-only",
                "reviewed_at": "2026-08-08T12:00:00+08:00",
                "review_artifact_sha256": "a" * 64,
            },
        }
    )
    math_result = integrate_numeric_grid_unqualified(
        wavelengths_nm=wavelengths,
        illuminant_spd=[1] * len(wavelengths),
        x_bar=xbar,
        y_bar=ybar,
        z_bar=zbar,
        reflectance=[1] * len(wavelengths),
    )
    with patch.object(
        spectral, "D65_REFERENCE_WHITE_XYZ", tuple(math_result["white_xyz"])
    ):
        yield compile_authoritative_standard_table(
            d65_csv_bytes=d65,
            cmf_csv_bytes=cmf,
            authority_manifest=authority,
        )


def _qualification(table: dict[str, object]) -> dict[str, object]:
    return seal_instrument_qualification(
        {
            "schema_version": 1,
            "kind": INSTRUMENT_KIND,
            "qualification_id": "n5-structural-test-instrument",
            "qualified": True,
            "instrument": {
                "category": "spectrophotometer",
                "manufacturer": "Test Instrument Co",
                "model": "STRUCTURAL-ONLY",
                "serial_number": "TEST-001",
                "firmware_version": "1.0",
                "configuration_sha256": "b" * 64,
            },
            "calibration": {
                "certificate_id": "CERT-STRUCTURAL-001",
                "calibration_lab": "Structural Test Lab",
                "calibrated_at": "2026-01-01T00:00:00Z",
                "calibration_due_at": "2027-01-01T00:00:00Z",
                "certificate_artifact_sha256": "c" * 64,
                "traceability": "structural test chain",
                "expanded_uncertainty_delta_e00": 0.2,
            },
            "optical_geometry": {
                "geometry": "45/0",
                "spectral_start_nm": 360,
                "spectral_end_nm": 830,
                "spectral_interval_nm": 5,
                "aperture_mm": 2.0,
                "panel_normal_error_deg": 0.5,
                "fixture_review_artifact_sha256": "d" * 64,
            },
            "repeatability": {
                "stationary_sample_count": 10,
                "repositioned_sample_count": 10,
                "session_count": 2,
                "passed": True,
                "report_artifact_sha256": "e" * 64,
            },
            "review": {
                "approved": True,
                "reviewer_id": "instrument-reviewer",
                "reviewed_at": "2026-08-01T00:00:00Z",
                "review_artifact_sha256": "f" * 64,
            },
        }
    )


def _reflectance(code: int, wavelengths: list[int]) -> list[float]:
    if code == 0:
        return [0.02] * len(wavelengths)
    if code == 1:
        return [0.92] * len(wavelengths)
    if code == 3:
        return [0.03 + 0.9 * math.exp(-0.5 * ((value - 625) / 48) ** 2) for value in wavelengths]
    if code == 6:
        return [0.03 + 0.9 * math.exp(-0.5 * ((value - 535) / 38) ** 2) for value in wavelengths]
    if code == 5:
        return [0.03 + 0.9 * math.exp(-0.5 * ((value - 445) / 35) ** 2) for value in wavelengths]
    if code == 2:
        return [
            min(
                0.95,
                0.03
                + 0.8 * math.exp(-0.5 * ((value - 570) / 70) ** 2)
                + 0.4 * math.exp(-0.5 * ((value - 625) / 60) ** 2),
            )
            for value in wavelengths
        ]
    raise AssertionError(code)


def _formal_palette_fixture(
    table: dict[str, object], qualification: dict[str, object]
) -> tuple[
    dict[str, object],
    list[dict[str, object]],
    dict[str, object],
    dict[str, object],
]:
    manifest = compile_campaign_manifest(
        panel=_bound_panel(),
        formal_palette_cold_profile=reviewed_panel_cold_profile(
            minimum_panel_power_off_seconds=60,
            review_artifact_sha256="1" * 64,
        ),
        waveform_id="wf-structural-v1",
        waveform_sha256="2" * 64,
        temperature_c=23.0,
        relative_humidity_percent=45.0,
        environment_record_sha256="3" * 64,
        standard_table_canonical_sha256=table["integrity"]["canonical_sha256"],
        instrument_qualification_canonical_sha256=qualification["integrity"][
            "canonical_sha256"
        ],
        pixel_pitch_review_artifact_sha256="4" * 64,
        roi_aperture_fit_review_artifact_sha256="5" * 64,
        orientation_bias_max_delta_e00=10.0,
        u95_max_delta_e00=10.0,
        acceptance_span_delta_e00=10.0,
        acceptance_review_artifact_sha256="6" * 64,
        acquisition_feasibility_review_artifact_sha256="7" * 64,
    )
    plan = manifest["formal_palette_plan"]
    assert plan["readiness"]["measurement_ready"] is True
    contract = execution.compile_execution_contract(manifest)
    wavelengths = [row["wavelength_nm"] for row in table["rows"]]
    payloads = []
    bindings_by_action: dict[str, list[dict[str, object]]] = {}
    for index, slot in enumerate(plan["expected_slots"]):
        measurement_id = f"n5-palette-structural-{index:03d}"
        reflectance = seal_reflectance_record(
            {
                "schema_version": 1,
                "kind": REFLECTANCE_KIND,
                "measurement_id": measurement_id,
                "grid": table["grid"],
                "reflectance": _reflectance(slot["code"], wavelengths),
                "raw_spectrum_artifact_sha256": _hash_text(f"raw-{index}"),
                "measurement_record_sha256": _hash_text(f"measurement-{index}"),
                "instrument_qualification_sha256": qualification["integrity"][
                    "canonical_sha256"
                ],
            }
        )
        report = integrate_reflectance(table, reflectance)
        run_key = f"{slot['orientation']}-{slot['formal_run']}"
        source_run_sha = _hash_text(f"run-{run_key}")
        asset_sha = _hash_text(f"asset-{run_key}")
        report_sha = spectral_report_file_sha256(report)
        target_sha = slot["target_action_identity_sha256"]
        bindings_by_action.setdefault(target_sha, []).append(
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
                "kind": PALETTE_OBSERVATION_KIND,
                "plan_canonical_sha256": plan["integrity"]["canonical_sha256"],
                "slot_id": slot["slot_id"],
                "context": plan["context"],
                "captured_at": "2026-08-08T12:00:00+08:00",
                "seconds_after_pof_busy_high": 55.0 + slot["measurement_order"],
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
    terminals = sorted(set(bindings_by_action))
    bundle = build_pass_bundle(
        contract,
        terminal_action_identity_sha256s=terminals,
        measurement_bindings_by_action=bindings_by_action,
    )
    summary = execution.validate_finalized_bundle(contract, bundle)
    observations = []
    for payload in payloads:
        primer = summary["actions_by_sha"][payload["primer_action_identity_sha256"]]
        target = summary["actions_by_sha"][payload["target_action_identity_sha256"]]
        payload.update(
            {
                "execution_contract_canonical_sha256": contract["integrity"][
                    "canonical_sha256"
                ],
                "finalized_bundle_canonical_sha256": bundle["integrity"][
                    "canonical_sha256"
                ],
                "authorization_id": target["authorization_id"],
                "primer_result_file_sha256": primer["result_file_sha256"],
                "target_result_file_sha256": target["result_file_sha256"],
            }
        )
        observations.append(
            seal_palette_observation(
                payload,
                plan=plan,
                standard_table=table,
                instrument_qualification=qualification,
            )
        )
    return plan, observations, contract, bundle


_LAB_BY_CODE = {
    0: {"l": 5.0, "a": 0.0, "b": 0.0},
    1: {"l": 95.0, "a": 0.0, "b": 0.0},
    2: {"l": 85.0, "a": 5.0, "b": 80.0},
    3: {"l": 50.0, "a": 70.0, "b": 40.0},
    5: {"l": 35.0, "a": 25.0, "b": -70.0},
    6: {"l": 55.0, "a": -60.0, "b": 35.0},
}


def _formal_transition_fixture():
    table_sha = "8" * 64
    qualification_sha = "9" * 64
    cold = reviewed_panel_cold_profile(
        minimum_panel_power_off_seconds=60,
        review_artifact_sha256="1" * 64,
    )
    recovery = build_reviewed_transition_recovery_profile(
        panel=_bound_panel(),
        firmware=DEFAULT_FIRMWARE,
        waveform_id="wf-transition-v1",
        waveform_sha256="a" * 64,
        qualification_artifact_sha256="e" * 64,
        reviewer_id="transition-structural-reviewer",
        reviewed_at="2026-08-08T00:00:00Z",
        review_artifact_sha256="f" * 64,
        supplier_limit_profile_sha256="1" * 64,
        usage_limit_contract_sha256="2" * 64,
        temperature_chain_sha256="3" * 64,
    )
    manifest = compile_campaign_manifest(
        panel=_bound_panel(),
        formal_transition_recovery_profile=recovery,
        formal_transition_power_profile=cold,
        waveform_id="wf-transition-v1",
        waveform_sha256="a" * 64,
        temperature_c=23.0,
        relative_humidity_percent=45.0,
        environment_record_sha256="b" * 64,
        standard_table_canonical_sha256=table_sha,
        instrument_qualification_canonical_sha256=qualification_sha,
        pixel_pitch_review_artifact_sha256="c" * 64,
        roi_aperture_fit_review_artifact_sha256="d" * 64,
    )
    plan = manifest["formal_transition_plan"]
    contract = execution.compile_execution_contract(manifest)
    table = {"integrity": {"canonical_sha256": table_sha}}
    qualification = {"integrity": {"canonical_sha256": qualification_sha}}

    def report_hash(report):
        return _hash_text(repr(sorted(report["lab"].items())))

    patches = contextlib.ExitStack()
    patches.enter_context(
        patch.object(aggregation, "validate_authoritative_standard_table", side_effect=lambda value: value)
    )
    patches.enter_context(
        patch.object(aggregation, "validate_instrument_qualification", side_effect=lambda value: value)
    )
    patches.enter_context(
        patch.object(aggregation, "instrument_qualification_blockers", return_value=[])
    )
    patches.enter_context(
        patch.object(aggregation, "validate_reflectance_record", side_effect=lambda value: value)
    )
    patches.enter_context(
        patch.object(aggregation, "validate_spectral_report", side_effect=lambda value, **_: value)
    )
    patches.enter_context(
        patch.object(aggregation, "spectral_report_file_sha256", side_effect=report_hash)
    )
    payloads = []
    bindings_by_action: dict[str, list[dict[str, object]]] = {}
    for index, slot in enumerate(plan["expected_slots"]):
        old = slot["old_code"]
        new = slot["new_code"]
        repeat = slot["formal_repeat"]
        controller_offset = 0.1 if slot["controller"] == "CS2" else 0.0
        initial_report = {"lab": dict(_LAB_BY_CODE[old])}
        final_report = {"lab": dict(_LAB_BY_CODE[new])}
        initial_reflectance = {
            "measurement_id": f"transition-initial-{index:03d}",
            "measurement_record_sha256": _hash_text(f"initial-measurement-{index}"),
            "raw_spectrum_artifact_sha256": _hash_text(f"initial-raw-{index}"),
            "instrument_qualification_sha256": qualification_sha,
        }
        final_reflectance = {
            "measurement_id": f"transition-final-{index:03d}",
            "measurement_record_sha256": _hash_text(f"final-measurement-{index}"),
            "raw_spectrum_artifact_sha256": _hash_text(f"final-raw-{index}"),
            "instrument_qualification_sha256": qualification_sha,
        }
        source_run_sha = _hash_text(f"transition-run-{repeat}")
        asset_sha = _hash_text(f"transition-asset-{repeat}")
        initial_report_sha = report_hash(initial_report)
        final_report_sha = report_hash(final_report)
        metrics = {
            "uniformity_delta_e00": 0.2 * repeat + controller_offset,
            "ghosting_metric": 0.1 * repeat + controller_offset,
            "busy_ms": 100.0 + repeat + controller_offset,
            "peak_current_a": 0.2 + 0.01 * repeat + controller_offset / 100,
            "energy_j": 1.0 + 0.1 * repeat + controller_offset,
            "temperature_rise_c": 0.5 + 0.1 * repeat + controller_offset,
            "recovery_pass": True,
        }
        initial_sha = slot["primer_action_identity_sha256"]
        target_sha = slot["target_action_identity_sha256"]
        bindings_by_action.setdefault(initial_sha, []).append(
            {
                "slot_id": slot["slot_id"],
                "measurement_phase": "transition_initial",
                "source_run_sha256": source_run_sha,
                "asset_manifest_sha256": asset_sha,
                "measurement_record_sha256": initial_reflectance[
                    "measurement_record_sha256"
                ],
                "raw_spectrum_artifact_sha256": initial_reflectance[
                    "raw_spectrum_artifact_sha256"
                ],
                "spectral_report_file_sha256": initial_report_sha,
                "metrics_sha256": None,
            }
        )
        bindings_by_action.setdefault(target_sha, []).append(
            {
                "slot_id": slot["slot_id"],
                "measurement_phase": "transition_final",
                "source_run_sha256": source_run_sha,
                "asset_manifest_sha256": asset_sha,
                "measurement_record_sha256": final_reflectance[
                    "measurement_record_sha256"
                ],
                "raw_spectrum_artifact_sha256": final_reflectance[
                    "raw_spectrum_artifact_sha256"
                ],
                "spectral_report_file_sha256": final_report_sha,
                "metrics_sha256": execution._sha256(metrics),
            }
        )
        payloads.append(
            {
                "schema_version": 1,
                "kind": TRANSITION_OBSERVATION_KIND,
                "plan_canonical_sha256": plan["integrity"]["canonical_sha256"],
                "slot_id": slot["slot_id"],
                "context": plan["context"],
                "captured_at": f"2026-08-08T12:{repeat:02d}:00+08:00",
                "source_run_sha256": source_run_sha,
                "asset_manifest_sha256": asset_sha,
                "authorization_id": None,
                "primer_action_identity_sha256": initial_sha,
                "target_action_identity_sha256": target_sha,
                "primer_result_file_sha256": None,
                "target_result_file_sha256": None,
                "initial_reflectance_record": initial_reflectance,
                "initial_spectral_report": initial_report,
                "initial_spectral_report_file_sha256": initial_report_sha,
                "final_reflectance_record": final_reflectance,
                "final_spectral_report": final_report,
                "final_spectral_report_file_sha256": final_report_sha,
                "metrics": metrics,
            }
        )
    terminals = sorted(
        {
            slot["target_action_identity_sha256"]
            for slot in plan["expected_slots"]
        }
    )
    bundle = build_pass_bundle(
        contract,
        terminal_action_identity_sha256s=terminals,
        measurement_bindings_by_action=bindings_by_action,
    )
    summary = execution.validate_finalized_bundle(contract, bundle)
    observations = []
    for payload in payloads:
        primer = summary["actions_by_sha"][payload["primer_action_identity_sha256"]]
        target = summary["actions_by_sha"][payload["target_action_identity_sha256"]]
        payload.update(
            {
                "execution_contract_canonical_sha256": contract["integrity"][
                    "canonical_sha256"
                ],
                "finalized_bundle_canonical_sha256": bundle["integrity"][
                    "canonical_sha256"
                ],
                "authorization_id": target["authorization_id"],
                "primer_result_file_sha256": primer["result_file_sha256"],
                "target_result_file_sha256": target["result_file_sha256"],
            }
        )
        observations.append(
            seal_transition_observation(
                payload,
                plan=plan,
                standard_table=table,
                instrument_qualification=qualification,
            )
        )
    return (
        plan,
        table,
        qualification,
        observations,
        patches,
        report_hash,
        contract,
        bundle,
    )


class SummaryAndQualificationTests(unittest.TestCase):
    def test_n_less_than_ten_never_reports_p95_or_p99(self) -> None:
        small = summarize_numeric([1, 2, 3, 4, 5, 6, 7, 8, 9])
        self.assertIsNone(small["p95"])
        self.assertIsNone(small["p99"])
        self.assertEqual(small["maximum_observed"], 9.0)
        ten = summarize_numeric(list(range(1, 11)))
        self.assertIsNotNone(ten["p95"])
        self.assertIsNotNone(ten["p99"])

    def test_instrument_cannot_qualify_by_flipping_flag(self) -> None:
        with _structural_table() as table:
            qualified = _qualification(table)
            draft = copy.deepcopy(qualified)
            draft.pop("integrity")
            draft["qualified"] = False
            draft["calibration"]["certificate_artifact_sha256"] = None
            draft = seal_instrument_qualification(draft)
            promoted = copy.deepcopy(draft)
            promoted["qualified"] = True
            with self.assertRaises(MeasurementAggregationError):
                validate_instrument_qualification(promoted)


class PaletteAggregationTests(unittest.TestCase):
    def test_incomplete_or_unqualified_inputs_never_emit_palette(self) -> None:
        manifest = compile_campaign_manifest(
            panel=_bound_panel(),
            formal_palette_cold_profile=reviewed_panel_cold_profile(
                minimum_panel_power_off_seconds=60,
                review_artifact_sha256="1" * 64,
            ),
        )
        report = aggregate_measured_palette(
            manifest["formal_palette_plan"],
            [],
            standard_table=None,
            instrument_qualification=None,
        )
        self.assertIsNone(report["palette"])
        self.assertFalse(report["classification"]["measured"])
        self.assertIn("palette_required_samples_incomplete", report["blockers"])
        promoted = copy.deepcopy(report)
        promoted["classification"]["measured"] = True
        promoted["classification"]["calibrated"] = True
        with self.assertRaises(MeasurementAggregationError):
            validate_palette_aggregate(promoted)

    def test_complete_formal_hierarchy_can_emit_calibrated_palette(self) -> None:
        with _structural_table() as table:
            qualification = _qualification(table)
            plan, observations, contract, bundle = _formal_palette_fixture(
                table, qualification
            )
            report = aggregate_measured_palette(
                plan,
                observations,
                standard_table=table,
                instrument_qualification=qualification,
                execution_contract=contract,
                finalized_bundle=bundle,
            )
            self.assertEqual(report["accepted_sample_count"], 36)
            self.assertEqual(report["expected_sample_count"], 36)
            self.assertEqual(report["blockers"], [])
            self.assertTrue(report["classification"]["measured"])
            self.assertTrue(report["palette"]["calibrated"])
            for code in (0, 1, 2, 3, 5, 6):
                self.assertEqual(report["statistics"][f"code-{code}.l"]["n"], 6)
                self.assertIsNone(report["statistics"][f"code-{code}.l"]["p95"])

    def test_production_entry_rejects_core_only_synthetic_execution(self) -> None:
        with _structural_table() as table:
            qualification = _qualification(table)
            plan, observations, contract, bundle = _formal_palette_fixture(
                table, qualification
            )
            # The explicit offline research entry intentionally accepts the
            # structural fixture, while the production boundary must replay
            # real strict RC2G evidence and reject it.
            offline = aggregate_measured_palette(
                plan,
                observations,
                standard_table=table,
                instrument_qualification=qualification,
                execution_contract=contract,
                finalized_bundle=bundle,
            )
            self.assertTrue(offline["classification"]["measured"])
            with self.assertRaisesRegex(
                MeasurementAggregationError,
                "invalid|strict RC2G",
            ):
                aggregate_production_measured_palette(
                    plan,
                    observations,
                    standard_table=table,
                    instrument_qualification=qualification,
                    execution_contract=contract,
                    finalized_bundle=bundle,
                )

    def test_cross_panel_observation_is_rejected(self) -> None:
        with _structural_table() as table:
            qualification = _qualification(table)
            plan, observations, _contract, _bundle = _formal_palette_fixture(
                table, qualification
            )
            payload = copy.deepcopy(observations[0])
            payload.pop("integrity")
            payload["context"]["panel"]["serial"] = "OTHER-PANEL"
            with self.assertRaisesRegex(MeasurementAggregationError, "context changed"):
                seal_palette_observation(
                    payload,
                    plan=plan,
                    standard_table=table,
                    instrument_qualification=qualification,
                )

    def test_raw_spectrum_and_measurement_replay_across_slots_is_rejected(self) -> None:
        with _structural_table() as table:
            qualification = _qualification(table)
            plan, observations, contract, bundle = _formal_palette_fixture(
                table, qualification
            )
            replay = copy.deepcopy(observations[0])
            replay.pop("integrity")
            second_slot = next(
                slot
                for slot in plan["expected_slots"]
                if slot["orientation"]
                == plan["expected_slots"][0]["orientation"]
                and slot["formal_run"]
                == plan["expected_slots"][0]["formal_run"]
                and slot["slot_id"] != plan["expected_slots"][0]["slot_id"]
            )
            replay["slot_id"] = second_slot["slot_id"]
            replay["primer_action_identity_sha256"] = second_slot[
                "primer_action_identity_sha256"
            ]
            replay["target_action_identity_sha256"] = second_slot[
                "target_action_identity_sha256"
            ]
            replay = seal_palette_observation(
                replay,
                plan=plan,
                standard_table=table,
                instrument_qualification=qualification,
            )
            replaced = [
                replay if record["slot_id"] == second_slot["slot_id"] else record
                for record in observations
            ]
            with self.assertRaisesRegex(
                MeasurementAggregationError, "replayed|finalized"
            ):
                aggregate_measured_palette(
                    plan,
                    replaced,
                    standard_table=table,
                    instrument_qualification=qualification,
                    execution_contract=contract,
                    finalized_bundle=bundle,
                )

    def test_synthetic_observations_without_finalized_bundle_are_rejected(self) -> None:
        with _structural_table() as table:
            qualification = _qualification(table)
            plan, observations, _contract, _bundle = _formal_palette_fixture(
                table, qualification
            )
            with self.assertRaisesRegex(
                MeasurementAggregationError, "finalized bundle"
            ):
                aggregate_measured_palette(
                    plan,
                    observations,
                    standard_table=table,
                    instrument_qualification=qualification,
                )


class TransitionAggregationGateTests(unittest.TestCase):
    def test_descriptive_transition_always_keeps_all_null_scaffold(self) -> None:
        manifest = compile_campaign_manifest()
        report = aggregate_transition_profile(
            manifest["descriptive_transition_plan"],
            [],
            standard_table=None,
            instrument_qualification=None,
        )
        self.assertIsNone(report["measured_profile"])
        self.assertFalse(report["classification"]["measured"])
        self.assertTrue(
            all(cell["sample_count"] == 0 for cell in report["unmeasured_scaffold"]["cells"])
        )
        promoted = copy.deepcopy(report)
        promoted["classification"]["measured"] = True
        promoted["classification"]["calibrated"] = True
        with self.assertRaises(MeasurementAggregationError):
            validate_transition_aggregate(promoted)

    def test_complete_formal_360_slots_emit_five_repeat_profile(self) -> None:
        plan, table, qualification, observations, patches, _, contract, bundle = (
            _formal_transition_fixture()
        )
        try:
            report = aggregate_transition_profile(
                plan,
                observations,
                standard_table=table,
                instrument_qualification=qualification,
                execution_contract=contract,
                finalized_bundle=bundle,
            )
        finally:
            patches.close()
        self.assertEqual(report["accepted_sample_count"], 360)
        self.assertEqual(report["expected_sample_count"], 360)
        self.assertEqual(report["blockers"], [])
        self.assertTrue(report["classification"]["measured"])
        profile = report["measured_profile"]
        self.assertTrue(profile["hardware_tested"])
        self.assertTrue(all(cell["sample_count"] == 5 for cell in profile["cells"]))
        primary = report["statistics"]["0->1.delta_e00"]
        self.assertEqual(primary["n"], 5)
        self.assertIsNone(primary["p95"])
        self.assertIsNone(primary["p99"])
        self.assertIsNotNone(primary["u95"])
        paired = report["statistics"][
            "0->1.paired_controller_diagnostics.delta_e00"
        ]
        self.assertEqual(paired["n"], 10)
        self.assertIsNone(paired["p95"])
        self.assertIsNone(paired["p99"])
        self.assertEqual(
            paired["extreme_reporting"],
            "paired-controller-descriptive-no-population-percentiles",
        )

    def test_formal_missing_slot_keeps_profile_null(self) -> None:
        plan, table, qualification, observations, patches, _, contract, bundle = (
            _formal_transition_fixture()
        )
        try:
            report = aggregate_transition_profile(
                plan,
                observations[:-1],
                standard_table=table,
                instrument_qualification=qualification,
                execution_contract=contract,
                finalized_bundle=bundle,
            )
        finally:
            patches.close()
        self.assertIsNone(report["measured_profile"])
        self.assertFalse(report["classification"]["measured"])
        self.assertEqual(report["accepted_sample_count"], 359)
        self.assertIn("transition_required_samples_incomplete", report["blockers"])

    def test_formal_raw_spectrum_replay_is_rejected(self) -> None:
        plan, table, qualification, observations, patches, _, contract, bundle = (
            _formal_transition_fixture()
        )
        try:
            replayed = copy.deepcopy(observations)
            replayed[1]["initial_reflectance_record"] = copy.deepcopy(
                replayed[0]["initial_reflectance_record"]
            )
            # Re-seal only the observation envelope.  The individual spectral
            # gate is intentionally mocked in this aggregator isolation test;
            # cross-slot raw replay must still be caught by the aggregator.
            payload = replayed[1]
            payload.pop("integrity")
            replayed[1] = seal_transition_observation(
                payload,
                plan=plan,
                standard_table=table,
                instrument_qualification=qualification,
            )
            with self.assertRaisesRegex(
                MeasurementAggregationError, "replayed|finalized"
            ):
                aggregate_transition_profile(
                    plan,
                    replayed,
                    standard_table=table,
                    instrument_qualification=qualification,
                    execution_contract=contract,
                    finalized_bundle=bundle,
                )
        finally:
            patches.close()


if __name__ == "__main__":
    unittest.main()
