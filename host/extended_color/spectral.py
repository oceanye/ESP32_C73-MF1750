"""Fail-closed D65/1931 2-degree spectral-reflectance integration.

No standard-observer or illuminant samples are bundled here.  A qualified
table can only be compiled from caller-supplied raw CIE CSV bytes whose exact
SHA-256 identities and primary-source provenance are reviewed in a separate
authority manifest.  The mathematical helper is intentionally labelled
unqualified and cannot create a D65/2-degree report.
"""

from __future__ import annotations

import csv
from datetime import datetime
import hashlib
from io import StringIO
import json
import math
import re
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import urlparse


SCHEMA_VERSION = 1
AUTHORITY_KIND = "mf1750-n5-cie-table-authority-manifest"
TABLE_KIND = "mf1750-n5-d65-1931-2deg-standard-table"
REFLECTANCE_KIND = "mf1750-n5-spectral-reflectance-record"
REPORT_KIND = "mf1750-n5-d65-2deg-spectral-integration-report"

AUTHORITY_HASH_SCOPE = (
    "entire authority manifest excluding integrity; UTF-8 JSON sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
TABLE_HASH_SCOPE = AUTHORITY_HASH_SCOPE.replace("authority manifest", "standard table")
REFLECTANCE_HASH_SCOPE = AUTHORITY_HASH_SCOPE.replace(
    "authority manifest", "spectral reflectance record"
)
REPORT_HASH_SCOPE = AUTHORITY_HASH_SCOPE.replace(
    "authority manifest", "spectral integration report"
)

STANDARD_GRID_START_NM = 360
STANDARD_GRID_END_NM = 830
SUPPORTED_INTERVALS_NM = (1, 5)
D65_REFERENCE_WHITE_XYZ = (95.047, 100.0, 108.883)
D65_WHITE_TOLERANCE = (0.35, 1e-9, 0.50)

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_RFC3339_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)
_SOURCE_ROLES = ("d65_spd", "cie_1931_2deg_cmf")
_COLUMN_ORDERS = {
    "d65_spd": ["wavelength_nm", "relative_spd"],
    "cie_1931_2deg_cmf": ["wavelength_nm", "x_bar", "y_bar", "z_bar"],
}


class SpectralContractError(ValueError):
    """Spectral data, provenance, or a derived report failed closed."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise SpectralContractError(f"value is not canonical JSON data: {error}") from error


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SpectralContractError(f"could not snapshot canonical JSON: {error}") from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _integrity(unsigned: Mapping[str, Any], scope: str) -> dict[str, str]:
    return {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": scope,
    }


def _mapping(value: Any, *, label: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SpectralContractError(f"{label} must be an object")
    if set(value) != keys:
        missing = sorted(keys - set(value))
        extra = sorted(set(value) - keys)
        raise SpectralContractError(
            f"{label} keys differ from the contract; missing={missing}, extra={extra}"
        )
    return value


def _text(value: Any, *, label: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise SpectralContractError(f"{label} must be non-empty text")
    if any(ord(character) < 0x20 for character in value):
        raise SpectralContractError(f"{label} must not contain control characters")
    return value


def _hash(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise SpectralContractError(f"{label} must be a lowercase SHA-256")
    if value == "0" * 64:
        raise SpectralContractError(f"{label} must not be a placeholder SHA-256")
    return value


def _timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or _RFC3339_RE.fullmatch(value) is None:
        raise SpectralContractError(f"{label} must be a strict RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SpectralContractError(f"{label} is not a valid timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SpectralContractError(f"{label} must include a timezone")
    return parsed


def _number(
    value: Any,
    *,
    label: str,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpectralContractError(f"{label} must be a finite JSON number")
    result = float(value)
    if not math.isfinite(result):
        raise SpectralContractError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise SpectralContractError(f"{label} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise SpectralContractError(f"{label} must be at most {maximum}")
    return result


def _validate_grid(value: Any) -> Mapping[str, Any]:
    grid = _mapping(
        value,
        label="spectral grid",
        keys={"wavelength_unit", "start_nm", "end_nm", "interval_nm", "sample_count"},
    )
    if grid["wavelength_unit"] != "nm":
        raise SpectralContractError("spectral wavelength unit must be nm")
    if (
        type(grid["start_nm"]) is not int
        or grid["start_nm"] != STANDARD_GRID_START_NM
        or type(grid["end_nm"]) is not int
        or grid["end_nm"] != STANDARD_GRID_END_NM
        or type(grid["interval_nm"]) is not int
        or grid["interval_nm"] not in SUPPORTED_INTERVALS_NM
    ):
        raise SpectralContractError("spectral grid must be 360..830 nm at 1 or 5 nm")
    expected_count = (grid["end_nm"] - grid["start_nm"]) // grid["interval_nm"] + 1
    if type(grid["sample_count"]) is not int or grid["sample_count"] != expected_count:
        raise SpectralContractError("spectral grid sample_count is inconsistent")
    return grid


def seal_authority_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Seal source identities and a human review; this reads no source bytes."""

    if not isinstance(payload, Mapping) or "integrity" in payload:
        raise SpectralContractError("authority payload must omit integrity")
    unsigned = _snapshot(payload)
    manifest = {**unsigned, "integrity": _integrity(unsigned, AUTHORITY_HASH_SCOPE)}
    validate_authority_manifest(manifest)
    return manifest


def validate_authority_manifest(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _mapping(
        manifest,
        label="authority manifest",
        keys={"schema_version", "kind", "output_grid", "sources", "review", "integrity"},
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != AUTHORITY_KIND:
        raise SpectralContractError("authority manifest schema or kind is invalid")
    _validate_grid(root["output_grid"])
    sources = root["sources"]
    if not isinstance(sources, list) or len(sources) != 2:
        raise SpectralContractError("authority manifest requires exactly D65 and CMF sources")
    seen: set[str] = set()
    for index, value in enumerate(sources):
        source = _mapping(
            value,
            label=f"authority source {index}",
            keys={
                "role",
                "publisher",
                "authority_type",
                "dataset_identifier",
                "source_uri",
                "artifact_sha256",
                "csv",
            },
        )
        role = source["role"]
        if role not in _SOURCE_ROLES or role in seen:
            raise SpectralContractError("authority source roles must be D65 SPD and 1931 CMF")
        seen.add(role)
        if source["publisher"] != "CIE" or source["authority_type"] != "standards-body-primary-table":
            raise SpectralContractError("standard data source must be a primary CIE table")
        _text(source["dataset_identifier"], label=f"authority source {role} dataset identifier")
        uri = _text(source["source_uri"], label=f"authority source {role} URI")
        parsed = urlparse(uri)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not (
            hostname == "cie.co.at" or hostname.endswith(".cie.co.at")
        ):
            raise SpectralContractError("standard data URI must be HTTPS on the CIE domain")
        _hash(source["artifact_sha256"], label=f"authority source {role} artifact")
        csv_contract = _mapping(
            source["csv"],
            label=f"authority source {role} CSV contract",
            keys={"encoding", "delimiter", "header_rows", "column_order"},
        )
        if csv_contract["encoding"] not in {"utf-8", "utf-8-sig"}:
            raise SpectralContractError("CIE CSV encoding must be utf-8 or utf-8-sig")
        delimiter = csv_contract["delimiter"]
        if delimiter not in {",", ";", "\t"}:
            raise SpectralContractError("CIE CSV delimiter is unsupported")
        if type(csv_contract["header_rows"]) is not int or not 0 <= csv_contract["header_rows"] <= 10:
            raise SpectralContractError("CIE CSV header_rows must be an integer from 0 through 10")
        if csv_contract["column_order"] != _COLUMN_ORDERS[role]:
            raise SpectralContractError("CIE CSV column order differs from the frozen parser")
    if seen != set(_SOURCE_ROLES):
        raise SpectralContractError("authority manifest omits a standard source role")
    review = _mapping(
        root["review"],
        label="authority review",
        keys={"approved", "reviewer_id", "reviewed_at", "review_artifact_sha256"},
    )
    if review["approved"] is not True:
        raise SpectralContractError("CIE source authority review must be approved")
    _text(review["reviewer_id"], label="authority reviewer")
    _timestamp(review["reviewed_at"], label="authority reviewed_at")
    _hash(review["review_artifact_sha256"], label="authority review artifact")
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if integrity != _integrity(unsigned, AUTHORITY_HASH_SCOPE):
        raise SpectralContractError("authority manifest canonical integrity is invalid")
    return root


def _parse_source_csv(
    payload: bytes,
    *,
    source: Mapping[str, Any],
) -> dict[int, tuple[float, ...]]:
    if _sha256(payload) != source["artifact_sha256"]:
        raise SpectralContractError(f"{source['role']} raw source SHA-256 does not match")
    csv_contract = source["csv"]
    try:
        text = payload.decode(csv_contract["encoding"])
    except UnicodeDecodeError as error:
        raise SpectralContractError(f"{source['role']} CSV is not declared encoding") from error
    try:
        rows = list(csv.reader(StringIO(text), delimiter=csv_contract["delimiter"], strict=True))
    except csv.Error as error:
        raise SpectralContractError(f"{source['role']} CSV parsing failed: {error}") from error
    rows = rows[csv_contract["header_rows"] :]
    expected_columns = len(csv_contract["column_order"])
    result: dict[int, tuple[float, ...]] = {}
    for row_index, row in enumerate(rows, start=csv_contract["header_rows"] + 1):
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(row) != expected_columns:
            raise SpectralContractError(
                f"{source['role']} CSV row {row_index} has {len(row)} columns, expected {expected_columns}"
            )
        try:
            wavelength_float = float(row[0].strip())
            values = tuple(float(cell.strip()) for cell in row[1:])
        except ValueError as error:
            raise SpectralContractError(
                f"{source['role']} CSV row {row_index} is not numeric"
            ) from error
        if (
            not math.isfinite(wavelength_float)
            or not wavelength_float.is_integer()
            or any(not math.isfinite(value) for value in values)
        ):
            raise SpectralContractError(f"{source['role']} CSV row {row_index} is non-finite")
        wavelength = int(wavelength_float)
        if wavelength in result:
            raise SpectralContractError(f"{source['role']} CSV duplicates {wavelength} nm")
        if source["role"] == "d65_spd":
            if values[0] <= 0:
                raise SpectralContractError("D65 SPD samples must be positive")
        elif any(value < 0 for value in values) or not any(value > 0 for value in values):
            raise SpectralContractError("1931 2-degree CMF rows must be nonnegative and nonzero")
        result[wavelength] = values
    if not result:
        raise SpectralContractError(f"{source['role']} CSV contains no numeric samples")
    return result


def _trapezoid(values: Sequence[float], interval_nm: int) -> float:
    if len(values) < 2:
        raise SpectralContractError("spectral integration requires at least two samples")
    return interval_nm * (
        0.5 * values[0] + math.fsum(values[1:-1]) + 0.5 * values[-1]
    )


def _lab_from_xyz(
    xyz: Sequence[float], white_xyz: Sequence[float]
) -> tuple[float, float, float]:
    if len(xyz) != 3 or len(white_xyz) != 3 or any(value <= 0 for value in white_xyz):
        raise SpectralContractError("XYZ/Lab conversion requires positive three-channel white")
    delta = 6 / 29

    def forward(value: float) -> float:
        return value ** (1 / 3) if value > delta**3 else value / (3 * delta**2) + 4 / 29

    fx, fy, fz = (
        forward(float(component) / float(white))
        for component, white in zip(xyz, white_xyz)
    )
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def integrate_numeric_grid_unqualified(
    *,
    wavelengths_nm: Sequence[int],
    illuminant_spd: Sequence[int | float],
    x_bar: Sequence[int | float],
    y_bar: Sequence[int | float],
    z_bar: Sequence[int | float],
    reflectance: Sequence[int | float],
) -> dict[str, Any]:
    """Exercise the numerical kernel without making a CIE-authority claim.

    This helper is useful for mathematical tests and diagnostics only.  Its
    result contains ``authority_qualified=false`` and cannot be consumed by a
    measured-palette or transition-profile aggregator.
    """

    sequences = (illuminant_spd, x_bar, y_bar, z_bar, reflectance)
    count = len(wavelengths_nm)
    if count < 2 or any(len(sequence) != count for sequence in sequences):
        raise SpectralContractError("unqualified numeric grid arrays differ in length")
    if any(type(value) is not int for value in wavelengths_nm):
        raise SpectralContractError("unqualified wavelengths must be integer nm")
    intervals = [right - left for left, right in zip(wavelengths_nm, wavelengths_nm[1:])]
    if not intervals or intervals[0] <= 0 or any(value != intervals[0] for value in intervals):
        raise SpectralContractError("unqualified wavelengths must be strictly uniform")
    interval = intervals[0]
    spd = [_number(value, label="unqualified SPD", minimum=0) for value in illuminant_spd]
    xb = [_number(value, label="unqualified xbar", minimum=0) for value in x_bar]
    yb = [_number(value, label="unqualified ybar", minimum=0) for value in y_bar]
    zb = [_number(value, label="unqualified zbar", minimum=0) for value in z_bar]
    refl = [
        _number(value, label="unqualified reflectance", minimum=0, maximum=1)
        for value in reflectance
    ]
    denominator = _trapezoid([s * y for s, y in zip(spd, yb)], interval)
    if denominator <= 0:
        raise SpectralContractError("spectral normalization denominator must be positive")
    scale = 100 / denominator

    def channel(cmf: Sequence[float], samples: Sequence[float]) -> float:
        return scale * _trapezoid(
            [r * s * c for r, s, c in zip(samples, spd, cmf)], interval
        )

    white = tuple(channel(cmf, [1.0] * count) for cmf in (xb, yb, zb))
    xyz = tuple(channel(cmf, refl) for cmf in (xb, yb, zb))
    lab = _lab_from_xyz(xyz, white)
    return {
        "authority_qualified": False,
        "formal_d65_2deg_report": False,
        "algorithm": "uniform-grid-composite-trapezoid-normalized-Y100-v1",
        "wavelength_unit": "nm",
        "interval_nm": interval,
        "white_xyz": list(white),
        "xyz": list(xyz),
        "lab": list(lab),
        "blockers": ["external_authoritative_CIE_tables_not_supplied"],
    }


def compile_authoritative_standard_table(
    *,
    d65_csv_bytes: bytes,
    cmf_csv_bytes: bytes,
    authority_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile caller-supplied primary CIE tables into one frozen grid."""

    authority = validate_authority_manifest(authority_manifest)
    source_by_role = {source["role"]: source for source in authority["sources"]}
    d65 = _parse_source_csv(d65_csv_bytes, source=source_by_role["d65_spd"])
    cmf = _parse_source_csv(cmf_csv_bytes, source=source_by_role["cie_1931_2deg_cmf"])
    grid = authority["output_grid"]
    wavelengths = list(range(grid["start_nm"], grid["end_nm"] + 1, grid["interval_nm"]))
    missing_d65 = [wavelength for wavelength in wavelengths if wavelength not in d65]
    missing_cmf = [wavelength for wavelength in wavelengths if wavelength not in cmf]
    if missing_d65 or missing_cmf:
        raise SpectralContractError(
            f"authoritative source grid is incomplete; missing D65={missing_d65[:5]}, CMF={missing_cmf[:5]}"
        )
    rows = [
        {
            "wavelength_nm": wavelength,
            "d65_spd": d65[wavelength][0],
            "x_bar": cmf[wavelength][0],
            "y_bar": cmf[wavelength][1],
            "z_bar": cmf[wavelength][2],
        }
        for wavelength in wavelengths
    ]
    math_result = integrate_numeric_grid_unqualified(
        wavelengths_nm=wavelengths,
        illuminant_spd=[row["d65_spd"] for row in rows],
        x_bar=[row["x_bar"] for row in rows],
        y_bar=[row["y_bar"] for row in rows],
        z_bar=[row["z_bar"] for row in rows],
        reflectance=[1.0] * len(rows),
    )
    white = math_result["white_xyz"]
    for actual, expected, tolerance in zip(
        white, D65_REFERENCE_WHITE_XYZ, D65_WHITE_TOLERANCE
    ):
        if not math.isclose(actual, expected, rel_tol=0, abs_tol=tolerance):
            raise SpectralContractError(
                "compiled CIE tables do not reproduce the frozen D65/2-degree white point"
            )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": TABLE_KIND,
        "standard": {
            "illuminant": "CIE standard illuminant D65",
            "observer": "CIE 1931 2 degree standard colorimetric observer",
            "canonical_result_label": "D65/2deg",
        },
        "grid": _snapshot(grid),
        "authority_manifest": _snapshot(authority),
        "rows": rows,
        "rows_canonical_sha256": _sha256(rows),
        "white_point_xyz_Y100": white,
        "algorithm": {
            "integration": "uniform-grid-composite-trapezoid",
            "normalization": "k=100/integral(D65*ybar*d_lambda)",
            "xyz_scale": "Y100",
            "lab": "CIE-1976-Lab-using-table-derived-D65-white",
            "interpolation": "none",
            "extrapolation": "none",
        },
        "classification": {
            "external_authoritative_tables": True,
            "raw_source_bytes_sha256_verified": True,
            "authority_reviewed": True,
            "project_bundled_standard_samples": False,
            "network_io_performed": False,
            "device_io_performed": False,
        },
    }
    table = {**unsigned, "integrity": _integrity(unsigned, TABLE_HASH_SCOPE)}
    validate_authoritative_standard_table(table)
    return table


def validate_authoritative_standard_table(table: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _mapping(
        table,
        label="authoritative standard table",
        keys={
            "schema_version",
            "kind",
            "standard",
            "grid",
            "authority_manifest",
            "rows",
            "rows_canonical_sha256",
            "white_point_xyz_Y100",
            "algorithm",
            "classification",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != TABLE_KIND:
        raise SpectralContractError("standard table schema or kind is invalid")
    if root["standard"] != {
        "illuminant": "CIE standard illuminant D65",
        "observer": "CIE 1931 2 degree standard colorimetric observer",
        "canonical_result_label": "D65/2deg",
    }:
        raise SpectralContractError("standard table label changed")
    grid = _validate_grid(root["grid"])
    validate_authority_manifest(root["authority_manifest"])
    rows = root["rows"]
    if not isinstance(rows, list) or len(rows) != grid["sample_count"]:
        raise SpectralContractError("standard table row count differs from grid")
    expected_wavelengths = list(
        range(grid["start_nm"], grid["end_nm"] + 1, grid["interval_nm"])
    )
    for index, (row, wavelength) in enumerate(zip(rows, expected_wavelengths)):
        record = _mapping(
            row,
            label=f"standard table row {index}",
            keys={"wavelength_nm", "d65_spd", "x_bar", "y_bar", "z_bar"},
        )
        if record["wavelength_nm"] != wavelength or type(record["wavelength_nm"]) is not int:
            raise SpectralContractError("standard table wavelength grid changed")
        _number(record["d65_spd"], label=f"row {index} D65", minimum=0)
        if record["d65_spd"] <= 0:
            raise SpectralContractError("standard table D65 samples must be positive")
        cmfs = [
            _number(record[field], label=f"row {index} {field}", minimum=0)
            for field in ("x_bar", "y_bar", "z_bar")
        ]
        if not any(value > 0 for value in cmfs):
            raise SpectralContractError("standard table CMF row is all zero")
    if root["rows_canonical_sha256"] != _sha256(rows):
        raise SpectralContractError("standard table row identity is invalid")
    math_result = integrate_numeric_grid_unqualified(
        wavelengths_nm=expected_wavelengths,
        illuminant_spd=[row["d65_spd"] for row in rows],
        x_bar=[row["x_bar"] for row in rows],
        y_bar=[row["y_bar"] for row in rows],
        z_bar=[row["z_bar"] for row in rows],
        reflectance=[1.0] * len(rows),
    )
    white = root["white_point_xyz_Y100"]
    if not isinstance(white, list) or len(white) != 3:
        raise SpectralContractError("standard table white point is invalid")
    if any(
        not math.isclose(_number(actual, label="white point"), expected, rel_tol=0, abs_tol=1e-12)
        for actual, expected in zip(white, math_result["white_xyz"])
    ):
        raise SpectralContractError("standard table white point is inconsistent with rows")
    for actual, expected, tolerance in zip(
        white, D65_REFERENCE_WHITE_XYZ, D65_WHITE_TOLERANCE
    ):
        if not math.isclose(actual, expected, rel_tol=0, abs_tol=tolerance):
            raise SpectralContractError("standard table white point is outside D65 tolerance")
    if root["algorithm"] != {
        "integration": "uniform-grid-composite-trapezoid",
        "normalization": "k=100/integral(D65*ybar*d_lambda)",
        "xyz_scale": "Y100",
        "lab": "CIE-1976-Lab-using-table-derived-D65-white",
        "interpolation": "none",
        "extrapolation": "none",
    }:
        raise SpectralContractError("standard table algorithm contract changed")
    if root["classification"] != {
        "external_authoritative_tables": True,
        "raw_source_bytes_sha256_verified": True,
        "authority_reviewed": True,
        "project_bundled_standard_samples": False,
        "network_io_performed": False,
        "device_io_performed": False,
    }:
        raise SpectralContractError("standard table classification changed")
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if integrity != _integrity(unsigned, TABLE_HASH_SCOPE):
        raise SpectralContractError("standard table canonical integrity is invalid")
    return root


def seal_reflectance_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Seal one raw-reflectance measurement record without creating data."""

    if not isinstance(payload, Mapping) or "integrity" in payload:
        raise SpectralContractError("reflectance payload must omit integrity")
    unsigned = _snapshot(payload)
    record = {**unsigned, "integrity": _integrity(unsigned, REFLECTANCE_HASH_SCOPE)}
    validate_reflectance_record(record)
    return record


def validate_reflectance_record(record: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _mapping(
        record,
        label="reflectance record",
        keys={
            "schema_version",
            "kind",
            "measurement_id",
            "grid",
            "reflectance",
            "raw_spectrum_artifact_sha256",
            "measurement_record_sha256",
            "instrument_qualification_sha256",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != REFLECTANCE_KIND:
        raise SpectralContractError("reflectance record schema or kind is invalid")
    _text(root["measurement_id"], label="reflectance measurement_id")
    grid = _validate_grid(root["grid"])
    values = root["reflectance"]
    if not isinstance(values, list) or len(values) != grid["sample_count"]:
        raise SpectralContractError("reflectance values differ from the standard grid")
    for index, value in enumerate(values):
        _number(value, label=f"reflectance[{index}]", minimum=0, maximum=1)
    for field in (
        "raw_spectrum_artifact_sha256",
        "measurement_record_sha256",
        "instrument_qualification_sha256",
    ):
        _hash(root[field], label=f"reflectance {field}")
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if integrity != _integrity(unsigned, REFLECTANCE_HASH_SCOPE):
        raise SpectralContractError("reflectance record canonical integrity is invalid")
    return root


def _compile_integration_report(
    table: Mapping[str, Any], reflectance: Mapping[str, Any]
) -> dict[str, Any]:
    rows = table["rows"]
    wavelengths = [row["wavelength_nm"] for row in rows]
    math_result = integrate_numeric_grid_unqualified(
        wavelengths_nm=wavelengths,
        illuminant_spd=[row["d65_spd"] for row in rows],
        x_bar=[row["x_bar"] for row in rows],
        y_bar=[row["y_bar"] for row in rows],
        z_bar=[row["z_bar"] for row in rows],
        reflectance=reflectance["reflectance"],
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "standard_table_canonical_sha256": table["integrity"]["canonical_sha256"],
        "authority_manifest_canonical_sha256": table["authority_manifest"]["integrity"][
            "canonical_sha256"
        ],
        "reflectance_record_canonical_sha256": reflectance["integrity"]["canonical_sha256"],
        "raw_spectrum_artifact_sha256": reflectance["raw_spectrum_artifact_sha256"],
        "measurement_record_sha256": reflectance["measurement_record_sha256"],
        "instrument_qualification_sha256": reflectance["instrument_qualification_sha256"],
        "condition": {
            "illuminant": "D65",
            "observer": "2deg",
            "wavelength_unit": "nm",
            "start_nm": table["grid"]["start_nm"],
            "end_nm": table["grid"]["end_nm"],
            "interval_nm": table["grid"]["interval_nm"],
            "sample_count": table["grid"]["sample_count"],
        },
        "algorithm": _snapshot(table["algorithm"]),
        "white_point_xyz_Y100": math_result["white_xyz"],
        "xyz_Y100": math_result["xyz"],
        "lab": {
            "l": math_result["lab"][0],
            "a": math_result["lab"][1],
            "b": math_result["lab"][2],
        },
        "classification": {
            "authoritative_external_standard_table": True,
            "raw_reflectance_bound": True,
            "canonical_D65_2deg_derived_result": True,
            "palette_calibration_claim": False,
            "transition_profile_claim": False,
            "network_io_performed": False,
            "device_io_performed": False,
        },
    }
    return {**unsigned, "integrity": _integrity(unsigned, REPORT_HASH_SCOPE)}


def integrate_reflectance(
    standard_table: Mapping[str, Any], reflectance_record: Mapping[str, Any]
) -> dict[str, Any]:
    """Create a canonical D65/2-degree report from qualified external tables."""

    table = validate_authoritative_standard_table(standard_table)
    reflectance = validate_reflectance_record(reflectance_record)
    if reflectance["grid"] != table["grid"]:
        raise SpectralContractError("reflectance grid differs from the authoritative table")
    report = _compile_integration_report(table, reflectance)
    validate_spectral_report(report, standard_table=table, reflectance_record=reflectance)
    return report


def validate_spectral_report(
    report: Mapping[str, Any],
    *,
    standard_table: Mapping[str, Any],
    reflectance_record: Mapping[str, Any],
) -> Mapping[str, Any]:
    table = validate_authoritative_standard_table(standard_table)
    reflectance = validate_reflectance_record(reflectance_record)
    if reflectance["grid"] != table["grid"]:
        raise SpectralContractError("spectral report inputs use different grids")
    expected = _compile_integration_report(table, reflectance)
    if report != expected:
        raise SpectralContractError("spectral integration report is tampered or inconsistent")
    return report


def spectral_report_file_sha256(report: Mapping[str, Any]) -> str:
    root = _mapping(
        report,
        label="spectral report",
        keys={
            "schema_version",
            "kind",
            "standard_table_canonical_sha256",
            "authority_manifest_canonical_sha256",
            "reflectance_record_canonical_sha256",
            "raw_spectrum_artifact_sha256",
            "measurement_record_sha256",
            "instrument_qualification_sha256",
            "condition",
            "algorithm",
            "white_point_xyz_Y100",
            "xyz_Y100",
            "lab",
            "classification",
            "integrity",
        },
    )
    return _sha256(root)


__all__ = [
    "AUTHORITY_KIND",
    "D65_REFERENCE_WHITE_XYZ",
    "REFLECTANCE_KIND",
    "REPORT_KIND",
    "STANDARD_GRID_END_NM",
    "STANDARD_GRID_START_NM",
    "SUPPORTED_INTERVALS_NM",
    "SpectralContractError",
    "TABLE_KIND",
    "compile_authoritative_standard_table",
    "integrate_numeric_grid_unqualified",
    "integrate_reflectance",
    "seal_authority_manifest",
    "seal_reflectance_record",
    "spectral_report_file_sha256",
    "validate_authoritative_standard_table",
    "validate_authority_manifest",
    "validate_reflectance_record",
    "validate_spectral_report",
]
