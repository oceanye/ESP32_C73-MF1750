from __future__ import annotations

import contextlib
import copy
import hashlib
import math
from pathlib import Path
import unittest
from unittest.mock import patch

import host.extended_color.spectral as spectral
from host.extended_color.spectral import (
    AUTHORITY_KIND,
    REFLECTANCE_KIND,
    SpectralContractError,
    compile_authoritative_standard_table,
    integrate_numeric_grid_unqualified,
    integrate_reflectance,
    seal_authority_manifest,
    seal_reflectance_record,
    spectral_report_file_sha256,
    validate_authoritative_standard_table,
    validate_authority_manifest,
    validate_reflectance_record,
    validate_spectral_report,
)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _synthetic_csv_inputs() -> tuple[bytes, bytes, list[int], tuple[float, float, float]]:
    """Structural-test numbers only; never installed or presented as CIE data."""

    wavelengths = list(range(360, 831, 5))
    d65_rows = []
    cmf_rows = []
    xbar = []
    ybar = []
    zbar = []
    for wavelength in wavelengths:
        x = 0.01 + math.exp(-0.5 * ((wavelength - 610) / 45) ** 2)
        y = 0.01 + math.exp(-0.5 * ((wavelength - 545) / 40) ** 2)
        z = 0.01 + 1.4 * math.exp(-0.5 * ((wavelength - 450) / 32) ** 2)
        d65_rows.append(f"{wavelength},1.0")
        cmf_rows.append(f"{wavelength},{x:.17g},{y:.17g},{z:.17g}")
        xbar.append(x)
        ybar.append(y)
        zbar.append(z)
    d65 = ("\n".join(d65_rows) + "\n").encode()
    cmf = ("\n".join(cmf_rows) + "\n").encode()
    numeric = integrate_numeric_grid_unqualified(
        wavelengths_nm=wavelengths,
        illuminant_spd=[1.0] * len(wavelengths),
        x_bar=xbar,
        y_bar=ybar,
        z_bar=zbar,
        reflectance=[1.0] * len(wavelengths),
    )
    return d65, cmf, wavelengths, tuple(numeric["white_xyz"])


def _authority(d65: bytes, cmf: bytes) -> dict[str, object]:
    return seal_authority_manifest(
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
                    "dataset_identifier": "STRUCTURAL-TEST-NOT-A-CIE-DATASET",
                    "source_uri": "https://files.cie.co.at/structural-test-d65.csv",
                    "artifact_sha256": _sha(d65),
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
                    "dataset_identifier": "STRUCTURAL-TEST-NOT-A-CIE-DATASET",
                    "source_uri": "https://files.cie.co.at/structural-test-cmf.csv",
                    "artifact_sha256": _sha(cmf),
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
                "reviewer_id": "structural-test-reviewer",
                "reviewed_at": "2026-08-08T12:00:00+08:00",
                "review_artifact_sha256": "a" * 64,
            },
        }
    )


@contextlib.contextmanager
def _structural_table():
    d65, cmf, _, white = _synthetic_csv_inputs()
    authority = _authority(d65, cmf)
    # Production requires the frozen CIE D65 white.  This patch is restricted
    # to a structural unit test so invented rows can never become an artifact.
    with patch.object(spectral, "D65_REFERENCE_WHITE_XYZ", white):
        table = compile_authoritative_standard_table(
            d65_csv_bytes=d65,
            cmf_csv_bytes=cmf,
            authority_manifest=authority,
        )
        yield table


class UnqualifiedKernelTests(unittest.TestCase):
    def _integrate(self, reflectance: list[float]) -> dict[str, object]:
        return integrate_numeric_grid_unqualified(
            wavelengths_nm=[400, 500, 600, 700],
            illuminant_spd=[1, 1, 1, 1],
            x_bar=[0.2, 0.5, 1.0, 0.4],
            y_bar=[0.1, 1.0, 0.7, 0.2],
            z_bar=[1.2, 0.8, 0.2, 0.1],
            reflectance=reflectance,
        )

    def test_white_black_and_neutral_math(self) -> None:
        white = self._integrate([1, 1, 1, 1])
        black = self._integrate([0, 0, 0, 0])
        neutral = self._integrate([0.25, 0.25, 0.25, 0.25])
        self.assertAlmostEqual(white["lab"][0], 100.0, places=10)
        self.assertAlmostEqual(white["lab"][1], 0.0, places=10)
        self.assertAlmostEqual(white["lab"][2], 0.0, places=10)
        self.assertAlmostEqual(black["lab"][0], 0.0, places=10)
        self.assertAlmostEqual(black["lab"][1], 0.0, places=10)
        self.assertAlmostEqual(black["lab"][2], 0.0, places=10)
        for actual, reference in zip(neutral["xyz"], neutral["white_xyz"]):
            self.assertAlmostEqual(actual, reference * 0.25, places=10)
        self.assertAlmostEqual(neutral["lab"][1], 0.0, places=10)
        self.assertAlmostEqual(neutral["lab"][2], 0.0, places=10)
        self.assertFalse(neutral["authority_qualified"])
        self.assertFalse(neutral["formal_d65_2deg_report"])

    def test_bad_grid_nonfinite_and_out_of_range_fail(self) -> None:
        with self.assertRaises(SpectralContractError):
            integrate_numeric_grid_unqualified(
                wavelengths_nm=[400, 500, 601],
                illuminant_spd=[1, 1, 1],
                x_bar=[1, 1, 1],
                y_bar=[1, 1, 1],
                z_bar=[1, 1, 1],
                reflectance=[1, 1, 1],
            )
        with self.assertRaises(SpectralContractError):
            self._integrate([0, float("nan"), 0, 0])
        with self.assertRaises(SpectralContractError):
            self._integrate([0, 1.01, 0, 0])


class AuthorityAndTableTests(unittest.TestCase):
    def test_external_source_and_review_are_mandatory(self) -> None:
        d65, cmf, _, _ = _synthetic_csv_inputs()
        authority = _authority(d65, cmf)
        wrong_domain = copy.deepcopy(authority)
        wrong_domain["sources"][0]["source_uri"] = "https://example.com/d65.csv"
        with self.assertRaises(SpectralContractError):
            validate_authority_manifest(wrong_domain)
        unreviewed = copy.deepcopy(authority)
        unreviewed["review"]["approved"] = False
        with self.assertRaises(SpectralContractError):
            validate_authority_manifest(unreviewed)

    def test_raw_source_sha_and_grid_are_fail_closed(self) -> None:
        d65, cmf, _, white = _synthetic_csv_inputs()
        authority = _authority(d65, cmf)
        with patch.object(spectral, "D65_REFERENCE_WHITE_XYZ", white):
            with self.assertRaisesRegex(SpectralContractError, "raw source SHA"):
                compile_authoritative_standard_table(
                    d65_csv_bytes=d65 + b"tamper",
                    cmf_csv_bytes=cmf,
                    authority_manifest=authority,
                )
            missing = b"\n".join(d65.splitlines()[:-1]) + b"\n"
            changed = copy.deepcopy(authority)
            changed.pop("integrity")
            changed["sources"][0]["artifact_sha256"] = _sha(missing)
            changed = seal_authority_manifest(changed)
            with self.assertRaisesRegex(SpectralContractError, "grid is incomplete"):
                compile_authoritative_standard_table(
                    d65_csv_bytes=missing,
                    cmf_csv_bytes=cmf,
                    authority_manifest=changed,
                )

    def test_structural_compile_has_frozen_algorithm_and_zero_io(self) -> None:
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            with _structural_table() as table:
                self.assertEqual(table["grid"]["start_nm"], 360)
                self.assertEqual(table["grid"]["end_nm"], 830)
                self.assertEqual(table["grid"]["interval_nm"], 5)
                self.assertEqual(table["algorithm"]["interpolation"], "none")
                self.assertEqual(table["algorithm"]["extrapolation"], "none")
                self.assertTrue(table["classification"]["external_authoritative_tables"])
                self.assertFalse(table["classification"]["network_io_performed"])

    def test_table_row_and_authority_manifest_tamper_fail(self) -> None:
        with _structural_table() as table:
            row_tamper = copy.deepcopy(table)
            row_tamper["rows"][0]["d65_spd"] = 2.0
            with self.assertRaises(SpectralContractError):
                validate_authoritative_standard_table(row_tamper)
            source_tamper = copy.deepcopy(table)
            source_tamper["authority_manifest"]["sources"][0][
                "dataset_identifier"
            ] = "changed"
            with self.assertRaises(SpectralContractError):
                validate_authoritative_standard_table(source_tamper)

    def test_project_does_not_bundle_standard_sample_tables(self) -> None:
        candidates = [
            path
            for path in Path("host/extended_color").iterdir()
            if path.suffix.lower() in {".csv", ".tsv", ".dat"}
        ]
        self.assertEqual(candidates, [])


class ReflectanceAndReportTests(unittest.TestCase):
    def _record(self, table: dict[str, object], values: list[float]):
        return seal_reflectance_record(
            {
                "schema_version": 1,
                "kind": REFLECTANCE_KIND,
                "measurement_id": "structural-measurement-001",
                "grid": table["grid"],
                "reflectance": values,
                "raw_spectrum_artifact_sha256": "b" * 64,
                "measurement_record_sha256": "c" * 64,
                "instrument_qualification_sha256": "d" * 64,
            }
        )

    def test_reflectance_wrong_grid_nonfinite_range_and_placeholder_hash_fail(self) -> None:
        with _structural_table() as table:
            count = table["grid"]["sample_count"]
            wrong_grid = {
                "schema_version": 1,
                "kind": REFLECTANCE_KIND,
                "measurement_id": "bad",
                "grid": {**table["grid"], "interval_nm": 1, "sample_count": 471},
                "reflectance": [0.5] * 471,
                "raw_spectrum_artifact_sha256": "b" * 64,
                "measurement_record_sha256": "c" * 64,
                "instrument_qualification_sha256": "d" * 64,
            }
            record = seal_reflectance_record(wrong_grid)
            with self.assertRaisesRegex(SpectralContractError, "grid differs"):
                integrate_reflectance(table, record)
            for bad in (float("nan"), -0.01, 1.01):
                values = [0.5] * count
                values[0] = bad
                payload = {
                    "schema_version": 1,
                    "kind": REFLECTANCE_KIND,
                    "measurement_id": "bad-value",
                    "grid": table["grid"],
                    "reflectance": values,
                    "raw_spectrum_artifact_sha256": "b" * 64,
                    "measurement_record_sha256": "c" * 64,
                    "instrument_qualification_sha256": "d" * 64,
                }
                with self.assertRaises(SpectralContractError):
                    seal_reflectance_record(payload)
            placeholder = self._record(table, [0.5] * count)
            placeholder = copy.deepcopy(placeholder)
            placeholder["raw_spectrum_artifact_sha256"] = "0" * 64
            with self.assertRaises(SpectralContractError):
                validate_reflectance_record(placeholder)

    def test_report_is_recomputed_and_whole_file_hashed(self) -> None:
        with _structural_table() as table:
            record = self._record(table, [0.5] * table["grid"]["sample_count"])
            report = integrate_reflectance(table, record)
            validate_spectral_report(
                report, standard_table=table, reflectance_record=record
            )
            self.assertRegex(spectral_report_file_sha256(report), r"^[0-9a-f]{64}$")
            tampered = copy.deepcopy(report)
            tampered["lab"]["l"] += 0.1
            with self.assertRaises(SpectralContractError):
                validate_spectral_report(
                    tampered, standard_table=table, reflectance_record=record
                )


if __name__ == "__main__":
    unittest.main()
