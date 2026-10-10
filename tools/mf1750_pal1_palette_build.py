#!/usr/bin/env python3
"""Build the calibrated MF-1750 measured palette + gamut profile from PAL1.

No device, network, relay or camera access. Input is one PAL1 extraction
document in the LH3-dose photo-analyzer format (128 rows, column = code, 10
Lab samples per cell) plus the sealed PAL1 package contract. Output:

- host/color_pipeline/palettes/mf1750_measured_v1.json — palette schema v2
  with calibrated=true and structured calibration provenance (measurement_id +
  extraction artifact sha256). The six physical codes 0/1/2/3/5/6 take the
  cross-side median Lab of their column; columns 4 and 7 are kept in an
  extras retention block OUTSIDE the palette schema (the canonical hash never
  covers it). The schema's own physical-consistency rules and this tool's
  cross-side agreement gate are fail-closed.
- host/gamut_mapping/profiles/mf1750_measured_xyz_v1.json — measured
  6-point gamut profile (same document shape as the synthetic reference
  profile; characterization_level=measured_primaries), bound to the new
  palette's canonical sha256 and to the extraction artifact.

Cross-side consistency: per code, CS1 vs CS2 column-median Lab must agree
within |dL*| <= 3.0 and dE00 <= 5.0 (the frozen cross-controller screening
limits); any breach refuses the build. The code-7 white column's measured L*
against the 2026-09-17 bright reference 65.8 is the session calibration
coefficient, recorded in the extras measurement block.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.color_pipeline.color import delta_e_ciede2000  # noqa: E402
from host.color_pipeline.palette import palette_from_mapping  # noqa: E402
from host.gamut_mapping.profile import gamut_profile_from_mapping  # noqa: E402
from host.static_photo.common import verify_integrity  # noqa: E402
from host.static_photo.lightness_test import THRESHOLDS  # noqa: E402

KIND = "mf1750-pal1-palette-build-v1"
PHYSICAL = {0: "black", 1: "white", 2: "yellow", 3: "red", 5: "blue", 6: "green"}
RECORD_ONLY = (4, 7)
RECIPE = re.compile(r"(?:PAL1-C|PAL2-C|LH3D-S7-D)([0-7])-R([0-7])")
DEFAULT_PALETTE_OUT = ROOT / "host/color_pipeline/palettes/mf1750_measured_v1.json"
DEFAULT_PROFILE_OUT = ROOT / "host/gamut_mapping/profiles/mf1750_measured_xyz_v1.json"
BRIGHT_WHITE_LSTAR_20260917 = 65.8
CROSS_SIDE_MAX_DELTA_LSTAR = THRESHOLDS["cross_controller_delta_lstar_maximum"]
CROSS_SIDE_MAX_DELTA_E76 = THRESHOLDS["cross_controller_delta_e76_maximum"]
# Documented column-level robustness rule for intra-cell uniformity failures
# (PAL1 2026-09-25 bright batch, see the inset probe): an ROI eating the cell
# edge transition band trips single_pixel_uniform without the cell's median
# Lab moving. A uniformity failure is tolerated only when ALL of:
#   - the failure is single_pixel_uniform (quality_pass clip/scatter failures
#     stay hard-fail);
#   - at most 2 cells in the (controller, code) column fail;
#   - each failed cell's median Lab stays within delta-E76 <= 4.0 of the
#     column's 8-cell median (i.e. it is not a column outlier).
# The tolerated cells are recorded in the palette extras block; nothing is
# silently relaxed.
UNIFORMITY_COLUMN_RULE = {
    "max_failed_cells_per_column": 2,
    "cell_lab_max_delta_e76_from_column_median": 4.0,
    "scope": "single_pixel_uniform failures only; quality_pass (clip/scatter) "
             "failures remain hard-fail",
    "evidence": "PAL1_CAL_ANALYSIS_20260925_V1/inset-probe/inset-probe.json: "
                "uniform_p95 of the edge-contaminated cells drops below the "
                "4.0 gate at central_fraction 0.30 with column-median Lab "
                "stable (<=0.5 L*)",
}
REQUIRED_PROVENANCE = (
    "panel_id", "panel_batch", "instrument_calibration_date", "measured_at",
    "temperature_c", "temperature_tolerance_c", "relative_humidity_percent",
    "firmware_commit", "waveform_version",
)
RENDERING_PRESETS = {
    "relative-colorimetric": {
        "version": "1.0.0", "tone_gamma": 1.0, "compression_knee": 1.0,
        "saturation_boost": 0.0, "lightness_weight": 1.0, "chroma_weight": 1.0,
        "hue_weight": 1.0},
    "perceptual": {
        "version": "1.0.0", "tone_gamma": 0.92, "compression_knee": 0.72,
        "saturation_boost": 0.0, "lightness_weight": 1.25, "chroma_weight": 0.85,
        "hue_weight": 1.35},
    "saturation": {
        "version": "1.0.0", "tone_gamma": 1.0, "compression_knee": 0.88,
        "saturation_boost": 0.18, "lightness_weight": 0.8, "chroma_weight": 1.5,
        "hue_weight": 0.75},
}


class PaletteBuildError(ValueError):
    """Malformed evidence, identity mismatch, or failed consistency gate."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bind(path: Path) -> dict:
    data = Path(path).read_bytes()
    return {"path": str(Path(path).resolve()), "bytes": len(data), "sha256": _sha(data)}


def _lab(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise PaletteBuildError(f"{label} must be a 3-component Lab triple")
    result = []
    for component in value:
        if isinstance(component, bool) or not isinstance(component, (int, float)) \
                or not math.isfinite(component):
            raise PaletteBuildError(f"{label} components must be finite numbers")
        result.append(float(component))
    return tuple(result)


def column_endpoints(extraction):
    """Per (side, code) column-median Lab + noise from a PAL1 extraction."""
    if not isinstance(extraction, dict) or not isinstance(extraction.get("rows"), list):
        raise PaletteBuildError("extraction must be an object with rows")
    groups: dict[tuple[str, int], list] = {}
    for index, row in enumerate(extraction["rows"]):
        if not isinstance(row, dict):
            raise PaletteBuildError(f"row {index} must be an object")
        match = RECIPE.fullmatch(str(row.get("recipe_id")))
        controller = row.get("controller")
        if controller not in ("CS1", "CS2") or match is None:
            raise PaletteBuildError(f"row {index} controller/recipe malformed")
        code, grid_row = int(match.group(1)), int(match.group(2))
        if row.get("grid_col") != code or row.get("grid_row") != grid_row:
            raise PaletteBuildError(f"row {index} grid position disagrees with recipe id")
        if row.get("comparison_id") not in (f"PAL1_C{code}", f"PAL2_C{code}", f"DOSE_C{code}"):
            raise PaletteBuildError(f"row {index} comparison_id differs")
        if row.get("quality_pass") is not True:
            raise PaletteBuildError(
                f"row {index} ({controller} C{code} R{grid_row}) failed the "
                "extraction clip/scatter quality gate; the palette build is "
                "fail-closed")
        samples = row.get("lab_samples")
        if not isinstance(samples, list) or len(samples) != 10:
            raise PaletteBuildError(f"row {index} needs exactly 10 Lab samples")
        groups.setdefault((controller, code), []).append({
            "lab": _lab(row.get("lab_median"), f"row {index} lab_median"),
            "lstar_samples": [_lab(s, f"row {index} sample")[0] for s in samples],
            "grid_row": grid_row,
            "uniform": row.get("single_pixel_uniform") is True,
        })
    expected = {(c, code) for c in ("CS1", "CS2") for code in range(8)}
    if set(groups) != expected:
        raise PaletteBuildError("extraction must cover the 128 (side, code, row) cells")
    endpoints = {}
    tolerated = {}
    for key, cells in groups.items():
        if len(cells) != 8:
            raise PaletteBuildError(f"{key} must have 8 row cells")
        center = tuple(median(c["lab"][ch] for c in cells) for ch in range(3))
        failed = [c for c in cells if not c["uniform"]]
        if len(failed) > UNIFORMITY_COLUMN_RULE["max_failed_cells_per_column"]:
            raise PaletteBuildError(
                f"{key}: {len(failed)} uniformity-failed cells exceed the "
                "documented column rule")
        for c in failed:
            delta_e76 = math.dist(c["lab"], center)
            if delta_e76 > UNIFORMITY_COLUMN_RULE[
                    "cell_lab_max_delta_e76_from_column_median"]:
                raise PaletteBuildError(
                    f"{key} R{c['grid_row']}: uniformity-failed cell is a "
                    f"column outlier (delta-E76 {delta_e76:.2f} from the column "
                    "median); the build is fail-closed")
        if failed:
            tolerated["%s/C%d" % key] = [
                {"row": c["grid_row"],
                 "delta_e76_from_column_median": round(math.dist(c["lab"], center), 4)}
                for c in failed]
        lstar = [v for c in cells for v in c["lstar_samples"]]
        med = median(lstar)
        mad = median(abs(v - med) for v in lstar)
        mean = sum(lstar) / len(lstar)
        var = sum((v - mean) ** 2 for v in lstar) / (len(lstar) - 1)
        noise = max(5 * mad, 2.262 * math.sqrt(var) / math.sqrt(len(lstar)))
        endpoints[key] = {"lab_median": center, "noise_lstar": noise,
                          "cell_lab_medians": [c["lab"] for c in cells]}
    if tolerated:
        endpoints["uniformity_tolerated_cells"] = {
            "rule": UNIFORMITY_COLUMN_RULE, "columns": tolerated}
    return endpoints


def cross_side_check(endpoints):
    """Fail-closed CS1/CS2 agreement per code; returns per-code deltas."""
    deltas = {}
    for code in range(8):
        lab1 = endpoints[("CS1", code)]["lab_median"]
        lab2 = endpoints[("CS2", code)]["lab_median"]
        delta_l = lab2[0] - lab1[0]
        delta_e = delta_e_ciede2000(lab1, lab2)
        deltas[code] = {"delta_lstar": round(delta_l, 4),
                        "delta_e00": round(delta_e, 4)}
        if abs(delta_l) > CROSS_SIDE_MAX_DELTA_LSTAR or delta_e > CROSS_SIDE_MAX_DELTA_E76:
            raise PaletteBuildError(
                f"code {code} CS1/CS2 disagreement beyond the cross-controller "
                f"limits: dL*={delta_l:+.3f} dE00={delta_e:.3f}; palette build "
                "is fail-closed")
    return deltas


# Measured L535 role assignment (PAL1 bright batch, 2026-09-25): the L535
# active path's nibble-to-colour mapping on this panel is NOT the stock frame
# contract. Roles follow the strongest-coverage assignment from the measured
# columns: black=3 (darkest), white=7, yellow=4 (brightest chromatic), red=1
# (vivid magenta family), green=6, blue=0 (blue-grey). Codes 2 and 5 stay out
# (second green / second dark purple) and are retained in extras.
L535_ROLE_CODES = {"black": 3, "white": 7, "yellow": 4, "red": 1,
                   "green": 6, "blue": 0}


def build_palette(endpoints, deltas, measurement_id, artifact_sha256, contract,
                  white_code=7, render_path="otp", palette_id="mf1750-measured-v1",
                  role_codes=None):
    """Assemble the schema-v2 palette dict + schema-external extras block."""
    if render_path == "l535_r20":
        roles = dict(L535_ROLE_CODES if role_codes is None else role_codes)
        if sorted(roles) != sorted(PHYSICAL.values()) or len(set(roles.values())) != 6:
            raise PaletteBuildError("l535 role map must assign six roles to six "
                                    "distinct drive nibbles")
        entries = []
        for name in sorted(roles):
            code = roles[name]
            labs = [endpoints[(ctrl, code)]["lab_median"] for ctrl in ("CS1", "CS2")]
            center = tuple(round(median(lab[ch] for lab in labs), 4) for ch in range(3))
            entries.append({"code": code, "name": name, "lab": list(center)})
    else:
        entries = []
        for code, name in sorted(PHYSICAL.items()):
            labs = [endpoints[(ctrl, code)]["lab_median"] for ctrl in ("CS1", "CS2")]
            center = tuple(round(median(lab[ch] for lab in labs), 4) for ch in range(3))
            entries.append({"code": code, "name": name, "lab": list(center)})
    white_cs = {ctrl: endpoints[(ctrl, white_code)]["lab_median"][0] for ctrl in ("CS1", "CS2")}
    white_mean = sum(white_cs.values()) / 2
    calibration_coefficient = {
        "white_code": white_code,
        "bright_reference": "2026-09-17 bright session white column L*",
        "bright_reference_lstar": BRIGHT_WHITE_LSTAR_20260917,
        "measured_white_lstar_per_side": {k: round(v, 4) for k, v in white_cs.items()},
        "measured_white_lstar_mean": round(white_mean, 4),
        "ratio_bright_over_measured": round(BRIGHT_WHITE_LSTAR_20260917 / white_mean, 6),
        "delta_lstar_bright_minus_measured": round(
            BRIGHT_WHITE_LSTAR_20260917 - white_mean, 4),
        "note": "session calibration coefficient; camera-relative sessions are "
                "compared through their own white column, never pooled raw",
    }
    extras = {
        "outside_schema_retention": True,
        "note": "NOT part of palette schema v2 and NOT covered by its canonical "
                "hash; record-only retention for later intermediate-state work",
        "record_only_endpoints": {
            str(code): {
                "cs1_lab_median": [round(v, 4) for v in endpoints[("CS1", code)]["lab_median"]],
                "cs2_lab_median": [round(v, 4) for v in endpoints[("CS2", code)]["lab_median"]],
                "cross_side": deltas[code],
            }
            for code in RECORD_ONLY
        },
        "per_code_noise_lstar": {
            str(code): round(max(endpoints[("CS1", code)]["noise_lstar"],
                                 endpoints[("CS2", code)]["noise_lstar"]), 4)
            for code in range(8)
        },
        "measurement": {
            "measurement_id": measurement_id,
            "extraction_artifact_sha256": artifact_sha256,
            "contract_sha256": contract["contract_id"],
            "campaign_id": contract["campaign_id"],
            "action_sha256": contract["actions"][0]["action_id"],
            "frame_sha256": contract["actions"][0]["frame"]["sha256"],
            "white_calibration_coefficient": calibration_coefficient,
        },
    }
    if render_path == "l535_r20":
        used = set((L535_ROLE_CODES if role_codes is None else role_codes).values())
        extras["l535_role_codes"] = dict(L535_ROLE_CODES if role_codes is None else role_codes)
        extras["unused_measured_columns"] = {
            str(code): {
                "cs1_lab_median": [round(v, 4) for v in endpoints[("CS1", code)]["lab_median"]],
                "cs2_lab_median": [round(v, 4) for v in endpoints[("CS2", code)]["lab_median"]],
            }
            for code in range(8) if code not in used
        }
        extras["render_path_note"] = ("entry codes are L535 drive nibbles; the "
                                      "measured nibble-to-colour mapping is "
                                      "documented in extras.l535_role_codes")
    doc = {
        "schema_version": 2,
        "palette_id": palette_id,
        "calibrated": True,
        "source": "MF-1750 panel measurement, PAL1 single active action "
                  "(production render path), camera-relative D65/2deg Lab",
        "illuminant": "D65",
        "observer": "2deg",
        "notes": "Measured on the MF-1750 panel through the PAL1 calibration "
                 "chain; camera-relative Lab. Codes 4/7 retained in extras "
                 "outside the schema.",
        "calibration": {"measurement_id": measurement_id,
                        "artifact_sha256": artifact_sha256},
        "entries": entries,
        "extras": extras,
    }
    if render_path != "otp":
        doc["render_path"] = render_path
    return doc


def build_gamut_profile(palette, palette_obj, artifact_sha256, provenance, measurement_id,
                        render_path="otp", profile_id="mf1750-measured-xyz-v1"):
    """Assemble the measured 6-point gamut profile dict (sample-shaped)."""
    doc = {
        "schema_version": 1,
        "kind": "mf1750-gamut-profile",
        "profile_id": profile_id,
        "profile_version": "1.0.0",
        "pipeline_compatibility": {
            "color_pipeline_version": "2.0.0",
            "gamut_mapper_version": "1.0.0",
        },
        "palette": {
            "id": palette["palette_id"],
            "canonical_sha256": palette_obj.canonical_sha256,
        },
        "model": {
            "kind": "linear_xyz_convex_v1",
            "characterization_level": "measured_primaries",
            **({"render_path": render_path} if render_path != "otp" else {}),
            "approximation": True,
            "pure_sample_refs": [
                {"code": code,
                 "sample_id": f"{palette['palette_id']}-code-{code}",
                 "artifact_sha256": artifact_sha256}
                for code in sorted(entry["code"] for entry in palette["entries"])
            ],
            "mixture_samples": [],
        },
        "measurement": {
            "measurement_id": measurement_id,
            "raw_artifact_sha256": artifact_sha256,
            "units": "relative_cie_xyz_y1",
            "illuminant": "D65",
            "observer": "2deg",
            "geometry": provenance.get("geometry",
                                       "camera-relative full-panel 10-frame median"),
            "backing": provenance.get("backing", "dark bench"),
            "instrument": provenance.get("instrument",
                                         "VID_32E4:PID_4801 camera-relative"),
            "instrument_calibration_date": provenance["instrument_calibration_date"],
            "measured_at": provenance["measured_at"],
        },
        "panel": {
            "model": "MF-17506-M009F-T",
            "panel_id": provenance["panel_id"],
            "batch": provenance["panel_batch"],
        },
        "firmware": {
            "commit": provenance["firmware_commit"],
            "waveform_version": provenance["waveform_version"],
        },
        "environment": {
            "temperature_c": provenance["temperature_c"],
            "temperature_tolerance_c": provenance["temperature_tolerance_c"],
            "relative_humidity_percent": provenance["relative_humidity_percent"],
        },
        "rendering_presets": RENDERING_PRESETS,
        "trust": {
            "fingerprint_trust": "audit fingerprint only; not a digital signature or trust-store decision",
            "source_statement": "Measured MF-1750 6-primary palette from the PAL1 calibration chain; camera-relative D65/2deg Lab bound to the extraction artifact",
            "signature": None,
        },
    }
    payload = json.dumps(doc, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    doc["canonical_sha256"] = _sha(payload)
    return doc


def validate_provenance(provenance):
    if not isinstance(provenance, dict):
        raise PaletteBuildError("provenance must be a JSON object")
    missing = [key for key in REQUIRED_PROVENANCE if provenance.get(key) is None]
    if missing:
        raise PaletteBuildError(
            "measured characterization requires complete provenance; missing: "
            + ", ".join(missing))
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extraction", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True,
                        help="sealed PAL1 package directory (contract.json inside)")
    parser.add_argument("--provenance", type=Path, required=True,
                        help="JSON with panel/firmware/environment provenance fields")
    parser.add_argument("--measurement-id", default=None)
    parser.add_argument("--white-code", type=int, default=None,
                        help="code column used as the session white reference "
                             "(default: 7 for PAL1/dose extractions, 1 for "
                             "PAL2 production-path extractions)")
    parser.add_argument("--render-path", choices=("otp", "l535_r20"),
                        default="otp")
    parser.add_argument("--palette-out", type=Path, default=DEFAULT_PALETTE_OUT)
    parser.add_argument("--profile-out", type=Path, default=DEFAULT_PROFILE_OUT)
    args = parser.parse_args()
    for path in (args.palette_out, args.profile_out):
        if path.exists():
            raise SystemExit(f"output exists (O_EXCL): {path}")
    try:
        extraction = json.loads(args.extraction.read_text(encoding="utf-8"))
        if "integrity" in extraction:
            verify_integrity(extraction, "PAL1 extraction")
        contract = json.loads(
            (args.package / "contract.json").read_text(encoding="utf-8"))
        provenance = validate_provenance(
            json.loads(args.provenance.read_text(encoding="utf-8")))
        endpoints = column_endpoints(extraction)
        deltas = cross_side_check(endpoints)
        artifact_sha256 = _sha(args.extraction.read_bytes())
        measurement_id = args.measurement_id or (
            "PAL1-CAL-" + str(extraction.get("identity", {}).get("stage", "PAL1")))
        white_code = args.white_code
        if white_code is None:
            first_recipe = str(extraction["rows"][0].get("recipe_id"))
            white_code = 1 if first_recipe.startswith("PAL2-") else 7
        if white_code not in range(8):
            raise PaletteBuildError("white code must be in 0..7")
        if args.render_path == "l535_r20":
            palette_id = "mf1750-l535-measured-v1"
            profile_id = "mf1750-l535-measured-xyz-v1"
        else:
            palette_id = "mf1750-measured-v1"
            profile_id = "mf1750-measured-xyz-v1"
        palette = build_palette(endpoints, deltas, measurement_id,
                                artifact_sha256, contract, white_code,
                                render_path=args.render_path, palette_id=palette_id)
        sampling = extraction.get("roi_sampling")
        if isinstance(sampling, dict) and sampling.get("central_fraction") is not None:
            palette["extras"]["measurement"]["roi_central_fraction"] = \
                sampling["central_fraction"]
        if "uniformity_tolerated_cells" in endpoints:
            palette["extras"]["uniformity_tolerated_cells"] = \
                endpoints["uniformity_tolerated_cells"]
        palette_obj = palette_from_mapping(
            {k: v for k, v in palette.items() if k != "extras"})
        profile = build_gamut_profile(palette, palette_obj, artifact_sha256,
                                      provenance, measurement_id,
                                      render_path=args.render_path,
                                      profile_id=profile_id)
        # Roundtrip validation before anything touches disk.
        gamut_profile_from_mapping(profile, palette_obj)
    except (PaletteBuildError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"FAIL_STOP: {error}")
    for path, doc in ((args.palette_out, palette), (args.profile_out, profile)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "result": "PASS", "kind": KIND,
        "palette": str(args.palette_out),
        "palette_canonical_sha256": palette_obj.canonical_sha256,
        "profile": str(args.profile_out),
        "profile_canonical_sha256": profile["canonical_sha256"],
        "white_calibration_ratio": palette["extras"]["measurement"]
        ["white_calibration_coefficient"]["ratio_bright_over_measured"],
        "hardware_accessed": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
