#!/usr/bin/env python3
"""Palette v2 re-calibration from the daylight atlas batch (offline, no device).

Builds mf1750_l535_measured_v2.json (palette schema v2, render_path l535_r20
kept byte-compatible in structure) plus the derived gamut profile v2, using the
100%-coverage cell Labs measured in DITHER_ATLAS_DAYLIGHT_20261011_V1 (natural
morning daylight, illumination ratio 0.943).  v1 is frozen as historical
evidence and is not touched.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.color_pipeline.color import lab_to_srgb8  # noqa: E402
from host.color_pipeline.palette import (  # noqa: E402
    CalibrationProvenance,
    Palette,
    PaletteEntry,
    load_palette,
)

DAYLIGHT = ROOT / ".test-output/hardware/DITHER_ATLAS_DAYLIGHT_20261011_V1/offline/dither-atlas-daylight-measured.json"
V1_PALETTE = ROOT / "host/color_pipeline/palettes/mf1750_l535_measured_v1.json"
V2_PALETTE = ROOT / "host/color_pipeline/palettes/mf1750_l535_measured_v2.json"
V2_PROFILE = ROOT / "host/gamut_mapping/profiles/mf1750_l535_measured_xyz_v2.json"

RENDERING_PRESETS = {
    "relative-colorimetric": {"version": "1.0.0", "tone_gamma": 1.0, "compression_knee": 1.0,
                              "saturation_boost": 0.0, "lightness_weight": 1.0, "chroma_weight": 1.0,
                              "hue_weight": 1.0},
    "perceptual": {"version": "1.0.0", "tone_gamma": 0.92, "compression_knee": 0.72,
                   "saturation_boost": 0.0, "lightness_weight": 1.25, "chroma_weight": 0.85,
                   "hue_weight": 1.35},
    "saturation": {"version": "1.0.0", "tone_gamma": 1.0, "compression_knee": 0.88,
                   "saturation_boost": 0.18, "lightness_weight": 0.8, "chroma_weight": 1.2,
                   "hue_weight": 0.9},
}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _delta_e00(a, b):
    import math
    L1, a1, b1 = a; L2, a2, b2 = b
    avg_L = (L1 + L2) / 2
    C1 = math.hypot(a1, b1); C2 = math.hypot(a2, b2)
    avg_C = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(avg_C ** 7 / (avg_C ** 7 + 25 ** 7))) if avg_C > 0 else 0.5
    a1p = a1 * (1 + G); a2p = a2 * (1 + G)
    C1p = math.hypot(a1p, b1); C2p = math.hypot(a2p, b2)
    avg_Cp = (C1p + C2p) / 2
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if C1p > 0 else 0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if C2p > 0 else 0
    dLp = L2 - L1; dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    else:
        dh = h2p - h1p
        if dh > 180: dh -= 360
        elif dh < -180: dh += 360
        dhp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dh / 2))
    avg_Lp = (L1 + L2) / 2
    if C1p * C2p == 0:
        avg_hp = h1p + h2p
    else:
        dh = abs(h1p - h2p)
        avg_hp = (h1p + h2p + 360) / 2 if (dh > 180 and h1p + h2p < 360) else ((h1p + h2p - 360) / 2 if dh > 180 else (h1p + h2p) / 2)
    T = (1 - 0.17 * math.cos(math.radians(avg_hp - 30)) + 0.24 * math.cos(math.radians(2 * avg_hp))
         + 0.32 * math.cos(math.radians(3 * avg_hp + 6)) - 0.20 * math.cos(math.radians(4 * avg_hp - 63)))
    d_ro = 30 * math.exp(-(((avg_hp - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(avg_Cp ** 7 / (avg_Cp ** 7 + 25 ** 7)) if avg_Cp > 0 else 0
    Sl = 1 + 0.015 * ((avg_Lp - 50) ** 2) / math.sqrt(20 + (avg_Lp - 50) ** 2)
    Sc = 1 + 0.045 * avg_Cp
    Sh = 1 + 0.015 * avg_Cp * T
    Rt = -math.sin(math.radians(2 * d_ro)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dhp / Sh) ** 2 + Rt * (dCp / Sc) * (dhp / Sh))


def main() -> None:
    measured = json.loads(DAYLIGHT.read_text(encoding="utf-8"))
    endpoints = measured["endpoints_vs_palette"]
    v1 = load_palette(V1_PALETTE)

    v1_by_code = {e.code: e for e in v1.entries}
    entries = []
    drift = []
    for entry in v1.entries:
        code = entry.code
        m = endpoints[str(code)]
        new_lab = tuple(float(v) for v in m["measured_lab"])
        old_lab = tuple(float(v) for v in entry.lab)
        drift.append({
            "code": code, "name": entry.name,
            "v1_lab": list(old_lab), "v2_lab": list(new_lab),
            "delta_L": round(new_lab[0] - old_lab[0], 2),
            "delta_e00": round(_delta_e00(old_lab, new_lab), 2),
        })
        entries.append(PaletteEntry(code=code, name=entry.name, lab=new_lab,
                                    preview_rgb=lab_to_srgb8(new_lab)))

    palette = Palette(
        palette_id="mf1750-l535-measured-v2",
        entries=tuple(entries),
        calibrated=True,
        source=("MF-1750 panel re-measurement, DITHER_ATLAS daylight session "
                "(atlas 100% coverage cells), camera-relative D65/2deg Lab"),
        notes=("v2 = current steady-state truth measured 2026-10-11 morning "
               "window daylight (illumination ratio 0.943 vs the 09-17 reference). "
               "v1 = 09-25 PAL1 calibration, whose green endpoint (L*47.3) proved "
               "transient: green now measures L*30.5 in matched daylight. "
               "Mechanism open (panel aging vs LUT-state drift). "
               "Codes 2/5 remain record-only aliases, not addressable endpoints. "
               "OTP behavior is unchanged (render_path l535_r20 kept)."),
        calibration=CalibrationProvenance(
            measurement_id="DITHER_ATLAS_DAYLIGHT_20261011_V1",
            artifact_sha256=_sha(DAYLIGHT.read_bytes()),
        ),
        render_path="l535_r20",
    )

    palette_doc = {
        "schema_version": 2,
        "palette_id": palette.palette_id,
        "calibrated": palette.calibrated,
        "source": palette.source,
        "illuminant": palette.illuminant,
        "observer": palette.observer,
        "notes": palette.notes,
        "calibration": {
            "measurement_id": palette.calibration.measurement_id,
            "artifact_sha256": palette.calibration.artifact_sha256,
        },
        "extras": {
            "outside_schema_retention": True,
            "note": ("NOT part of palette schema v2 and NOT covered by its canonical "
                     "hash; record-only retention for later intermediate-state work"),
            "v1_reference": {
                "palette_id": v1.palette_id,
                "canonical_sha256": v1.canonical_sha256,
                "drift_table": drift,
                "note": ("v1 frozen as historical evidence; v2 is the current truth. "
                         "Green endpoint drifted 47.3 -> 30.5 L* between the two "
                         "calibrations (4 sessions, 2 light classes)."),
            },
        },
        "render_path": "l535_r20",
    }
    payload = json.dumps(palette_doc, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    palette_doc["canonical_sha256"] = _sha(payload)
    V2_PALETTE.write_text(json.dumps(palette_doc, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")

    artifact_sha = _sha(DAYLIGHT.read_bytes())
    profile_doc = {
        "schema_version": 1,
        "kind": "mf1750-gamut-profile",
        "profile_id": "mf1750-l535-measured-xyz-v2",
        "profile_version": "1.0.0",
        "pipeline_compatibility": {
            "color_pipeline_version": "2.0.0",
            "gamut_mapper_version": "1.0.0",
        },
        "palette": {
            "id": palette.palette_id,
            "canonical_sha256": palette.canonical_sha256,
        },
        "model": {
            "kind": "linear_xyz_convex_v1",
            "characterization_level": "measured_primaries",
            "render_path": "l535_r20",
            "approximation": True,
            "pure_sample_refs": [
                {"code": code,
                 "sample_id": f"mf1750-l535-measured-v2-code-{code}",
                 "artifact_sha256": artifact_sha}
                for code in sorted(entry.code for entry in palette.entries)
            ],
            "mixture_samples": [],
        },
        "measurement": {
            "measurement_id": "DITHER_ATLAS_DAYLIGHT_20261011_V1",
            "raw_artifact_sha256": artifact_sha,
            "units": "relative_cie_xyz_y1",
            "illuminant": "D65",
            "observer": "2deg",
            "geometry": "camera-relative full-panel 11-frame median",
            "backing": "dark bench",
            "instrument": "VID_32E4:PID_4801 camera-relative",
            "instrument_calibration_date": "2026-09-17",
            "measured_at": "2026-10-11T00:57:00+00:00",
        },
        "panel": {"model": "MF-17506-M009F-T", "panel_id": "MF1750-DEVKITC-B2-01",
                  "batch": "mf1750-devkitc-b2"},
        "firmware": {"commit": "cb25e57c424ad7c9be703268afe6d944800b2a636af938bc8713508763d204ae",
                     "waveform_version": "L535_ACTIVE_RUNTIME_FRAME_PATH_V1"},
        "environment": {"temperature_c": None, "temperature_tolerance_c": None,
                        "relative_humidity_percent": None},
        "rendering_presets": RENDERING_PRESETS,
        "trust": {
            "fingerprint_trust": "audit fingerprint only; not a digital signature or trust-store decision",
            "source_statement": ("Re-measured MF-1750 6-primary palette from the DITHER_ATLAS "
                                 "daylight session; camera-relative D65/2deg Lab bound to the "
                                 "daylight measured artifact"),
            "signature": None,
        },
    }
    payload2 = json.dumps(profile_doc, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    profile_doc["canonical_sha256"] = _sha(payload2)
    V2_PROFILE.write_text(json.dumps(profile_doc, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")

    print(json.dumps({
        "palette_v2": str(V2_PALETTE),
        "palette_v2_canonical_sha256": palette.canonical_sha256,
        "profile_v2": str(V2_PROFILE),
        "profile_v2_canonical_sha256": profile_doc["canonical_sha256"],
        "drift_table": drift,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
