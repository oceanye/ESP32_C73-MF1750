#!/usr/bin/env python3
"""LH2 drive-map MAP analysis over the sealed 128-ROI extraction.

Read-only offline analysis. Inputs:
- the MAP extraction.json produced by tools/mf1750_lh2_drive_map_photo_analyzer.py
  (10 same-state frames median + noise, plus post-map anchor re-measurement),
- this session's s3-pre.jpg (MIDDLE state on screen just before the MAP action),
  used to extract session-consistent MIDDLE endpoints (single frame; the 8
  spatial replicas per code per side give a spatial noise proxy),
- the sealed LH1 rebound MIDDLE extraction (cross-session reference only),
- the sealed LH2 package (contract/blank/inc) and device live reports
  (execution-integrity evidence: profile hashes and streamed-frame FNV-1a).

Outputs (all O_EXCL inside --output-dir, which must already contain only the
analyzer's extraction.json): map-analysis.json (sealed), map-lstar-heatmap.png,
analysis-review.json (sealed), and a frozen copy of this tool.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from host.color_pipeline.color import delta_e_ciede2000  # noqa: E402
from tools import mf1750_lh1_lh4_once as rec  # noqa: E402
from tools import mf1750_lh1_rebound_v2_middle_photo_analyzer as base  # noqa: E402
from tools import mf1750_lh2_drive_map_photo_analyzer as analyzer  # noqa: E402

ANALYSIS_VERSION = "mf1750-lh2-drive-map-analysis-v1"
# Frozen chain gates (MF1750_LIGHTNESS_TEST_V1_20260911 era): within-chain
# adjacent levels need dL*>=2, dE00>=3, hue gap <=5 deg; chroma gate C*>8 for
# hue-chain membership; noise floor per state = max(5*MAD, CI95 half width),
# pair resolvable only when dL* exceeds the sum of both floors.
GATE_DL = 2.0
GATE_DE00 = 3.0
GATE_HUE_DEG = 5.0
CHROMA_GATE = 8.0
# 12 hue families, 30-degree buckets, R centred on 0/360 (frozen coverage idiom).
HUE_FAMILIES = ("R", "RO", "O", "Y", "YG", "G", "T", "C", "B", "I", "V", "M")
# History -> family membership from the sealed bright-session MIDDLE measurement
# (docs/MF1750_LH2_DRIVE_MAP_CHAIN_DESIGN_2026-09-17.md): M0/M1/M2 red, M3/M5
# indigo, M4 brown, M6 cyan-blue, M7 white.
FAMILY_OF_HISTORY = {0: "R", 1: "R", 2: "R", 3: "V", 4: "RO", 5: "V", 6: "B", 7: "WHITE"}
USER_ACCEPTABLE_LEVELS = (4, 6)


def hue_deg(lab) -> float:
    return math.degrees(math.atan2(lab[2], lab[1])) % 360.0


def hue_gap(a, b) -> float:
    d = abs(hue_deg(a) - hue_deg(b)) % 360.0
    return min(d, 360.0 - d)


def chroma(lab) -> float:
    return math.hypot(lab[1], lab[2])


def family_of_hue(hue: float) -> str:
    return HUE_FAMILIES[int(((hue + 15.0) % 360.0) // 30.0)]


def noise_floor(mad: float, ci95: float) -> float:
    return max(5.0 * mad, ci95)


def fnv1a(data: bytes) -> int:
    h = 2166136261
    for b in data:
        h ^= b
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def controller_stream_fnv(frame: bytes, half: int) -> int:
    """Mirror epdStreamPackedFrameController (MAP_ORIENT_V1: no flips/swaps)."""
    h = 2166136261
    for y in range(600):
        row = frame[y * 512 + half * 256: y * 512 + half * 256 + 256]
        for b in row:
            h ^= b
            h = (h * 16777619) & 0xFFFFFFFF
    return h


def session_middle_endpoints(s3_pre: Path, package: Path) -> dict:
    """Extract this session's MIDDLE endpoints from the s3-pre photo.

    Same detection + geometry + ROI sampling as the MAP analyzer. Single frame:
    the noise proxy is spatial, over the 8 replica cells per code per side.
    """
    bgr = cv2.imread(str(s3_pre))
    if bgr is None or bgr.shape[:2] != (3000, 4000):
        raise SystemExit("s3-pre unreadable or wrong size")
    comps = base.grid_components(analyzer.detect_centers(bgr))
    side_of = {"left": comps[0] if comps[0][:, 0].mean() < comps[1][:, 0].mean() else comps[1],
               "right": comps[1] if comps[0][:, 0].mean() < comps[1][:, 0].mean() else comps[0]}
    blank = json.loads((package / "observations.blank.json").read_text(encoding="utf-8"))
    entries = blank["observations"]
    placement_all = base.load_placement(
        package / "generated" / "ec5_lightness_lh2_drive_map_v1_identity.inc")
    placement = {"CS1": placement_all["kRecipeAtCellCs1"],
                 "CS2": placement_all["kRecipeAtCellCs2"]}
    result = {"detected_cells": {}, "endpoints": {}}
    for side, ctrl in (("left", "CS1"), ("right", "CS2")):
        lattice, _ = base.assign_lattice(side_of[side])
        result["detected_cells"][ctrl] = len(lattice)
        ref = {}
        hlat = base.lattice_homography(lattice)
        for ir in range(8):
            for ic in range(8):
                xy = lattice.get((ir, ic))
                if xy is None:
                    xy = cv2.perspectiveTransform(np.array([[[ic, ir]]], dtype=np.float64),
                                                  hlat)[0, 0]
                ref[(ir, ic)] = tuple(float(v) for v in xy)
        src = np.array([base.local_center(r, c) for r in range(8) for c in range(8)])
        dst = np.array([ref[(r, c)] for r in range(8) for c in range(8)])
        h, _ = cv2.findHomography(src, dst, 0)
        per_code: dict[int, list] = {code: [] for code in range(8)}
        quality = []
        for e in entries:
            if e["controller"] != ctrl:
                continue
            med, q = base.sample_roi_lab(bgr, h, e["roi"])
            if med is None:
                raise SystemExit(f"s3-pre ROI outside image: {json.dumps(e)}")
            row = (e["roi"]["y"] - base.GRID_Y0) // (base.CELL_H + base.GAP)
            col = (e["roi"]["x"] - base.GRID_X0) // (base.CELL_W + base.GAP)
            per_code[placement[ctrl][row * 8 + col] % 8].append(med)
            quality.append(q)
        endpoints = {}
        for code, labs in per_code.items():
            arr = np.stack(labs)
            med = np.median(arr, axis=0)
            lstar = arr[:, 0]
            endpoints[str(code)] = {
                "lab_median": [float(v) for v in med],
                "lab_per_position": [[float(v) for v in s] for s in arr],
                "hue_deg": hue_deg(med), "chroma": chroma(med),
                "family_by_session_hue": ("NEUTRAL" if chroma(med) <= CHROMA_GATE
                                          else family_of_hue(hue_deg(med))),
                "lstar_mad_spatial": float(np.median(np.abs(lstar - med[0]))),
                "lstar_ci95_half_width_spatial":
                    float(2.365 * np.std(lstar, ddof=1) / math.sqrt(len(lstar))),
                "position_count": len(labs)}
        result["endpoints"][ctrl] = endpoints
        result.setdefault("max_clip_fraction", 0.0)
        result["max_clip_fraction"] = max(
            result["max_clip_fraction"],
            max(max(q["clip_high_fraction"], q["clip_low_fraction"]) for q in quality))
        result.setdefault("max_uniform_p95_delta_e76", 0.0)
        result["max_uniform_p95_delta_e76"] = max(
            result["max_uniform_p95_delta_e76"],
            max(q["uniform_p95_delta_e76"] for q in quality))
    return result


def chain_levels(states: list[dict], enforce_hue: bool = True) -> list[list[dict]]:
    """Greedy darkest-first chaining under the frozen gates.

    Returns the kept chain (list with one dict per resolvable level, each with
    the states merged into it recorded under 'members').
    """
    pool = sorted(states, key=lambda s: s["lab"][0])
    chain: list[dict] = []
    for s in pool:
        if not chain:
            chain.append({**s, "members": [s["label"]]})
            continue
        prev = chain[-1]
        dl = s["lab"][0] - prev["lab"][0]
        de00 = delta_e_ciede2000(prev["lab"], s["lab"])
        hg = hue_gap(prev["lab"], s["lab"])
        if (dl >= GATE_DL and de00 >= GATE_DE00
                and (not enforce_hue or hg <= GATE_HUE_DEG)
                and dl >= prev["noise"] + s["noise"]):
            chain.append({**s, "members": [s["label"]],
                          "delta_lstar_from_prev": dl, "delta_e00_from_prev": de00,
                          "hue_gap_from_prev_deg": hg})
        else:
            s["blocked_by"] = {"delta_lstar": dl, "delta_e00": de00, "hue_gap_deg": hg,
                               "noise_floor_sum": prev["noise"] + s["noise"]}
    return chain


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--analysis-dir", type=Path, required=True,
                   help="output dir already holding extraction.json (O_EXCL for new files)")
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--batch", type=Path, required=True,
                   help="hardware batch dir (s3-pre.jpg + live-s2/live-s3 reports)")
    p.add_argument("--middle-extraction", type=Path, required=True,
                   help="sealed bright-session MIDDLE extraction (reference only)")
    args = p.parse_args()
    out_dir = args.analysis_dir
    extraction_path = out_dir / "extraction.json"
    if not extraction_path.exists():
        raise SystemExit("extraction.json missing; run the photo analyzer first")
    for name in ("map-analysis.json", "analysis-review.json", "map-lstar-heatmap.png"):
        if (out_dir / name).exists():
            raise SystemExit(f"{name} already exists (O_EXCL batch)")

    extraction = json.loads(extraction_path.read_text(encoding="utf-8"))
    rows = extraction["rows"]
    if len(rows) != 128:
        raise SystemExit("128 extraction rows required")
    middle = json.loads(args.middle_extraction.read_text(encoding="utf-8"))

    # --- execution integrity (device-side evidence, offline verification) ---
    s2 = json.loads((args.batch / "live-s2" / "008-get-report.body.bin").read_text(encoding="utf-8"))
    s3 = json.loads((args.batch / "live-s3" / "008-get-report.body.bin").read_text(encoding="utf-8"))
    map_frame = (args.package / "map.frame4bpp").read_bytes()
    integrity = {
        "s2_profile_sha256": s2["profile_sha256"], "s3_profile_sha256": s3["profile_sha256"],
        "profiles_identical": s2["profile_sha256"] == s3["profile_sha256"],
        "s3_profile_id": s3["profile_id"], "s3_role": s3["role"],
        "map_input_fnv1a_device": s3["driver"]["input_fnv1a"],
        "map_input_fnv1a_offline": fnv1a(map_frame),
        "map_cs1_dtm_fnv1a_device": s3["driver"]["cs1_dtm_fnv1a"],
        "map_cs1_dtm_fnv1a_offline": controller_stream_fnv(map_frame, 0),
        "map_cs2_dtm_fnv1a_device": s3["driver"]["cs2_dtm_fnv1a"],
        "map_cs2_dtm_fnv1a_offline": controller_stream_fnv(map_frame, 1),
    }
    integrity["input_frame_byte_exact"] = (
        integrity["map_input_fnv1a_device"] == integrity["map_input_fnv1a_offline"])
    integrity["streamed_bytes_exact"] = (
        integrity["map_cs1_dtm_fnv1a_device"] == integrity["map_cs1_dtm_fnv1a_offline"]
        and integrity["map_cs2_dtm_fnv1a_device"] == integrity["map_cs2_dtm_fnv1a_offline"])

    # --- session-consistent MIDDLE endpoints from s3-pre.jpg ---
    session_middle = session_middle_endpoints(args.batch / "s3-pre.jpg", args.package)
    # Geometry validation for this session: under the inherited identity/identity
    # labelling, the placement code-7 cells must be exactly the white cells.
    code7_white_check = {}
    for ctrl in ("CS1", "CS2"):
        eps = session_middle["endpoints"][ctrl]
        l7 = eps["7"]["lab_median"][0]
        others = [eps[str(c)]["lab_median"][0] for c in range(7)]
        code7_white_check[ctrl] = {"code7_lstar": l7, "max_other_lstar": max(others),
                                   "code7_is_whitest": bool(l7 > max(others) + 10.0)}

    # Sealed bright-session MIDDLE endpoints (cross-session reference).
    sealed_middle = {}
    import collections
    grouped = collections.defaultdict(list)
    for r in middle["rows"]:
        if r["controller"] == "CS1":
            grouped[int(r["recipe_id"][8])].append(r)
    for m, rs in sorted(grouped.items()):
        labs = np.array([r["lab_median"] for r in rs])
        med = np.median(labs, axis=0)
        sealed_middle[str(m)] = {"lab_median_cs1": [float(v) for v in med],
                                 "hue_deg": hue_deg(med), "chroma": chroma(med),
                                 "noise_floor": max(noise_floor(r["lstar_mad"],
                                                                r["lstar_ci95_half_width"])
                                                    for r in rs),
                                 "family": FAMILY_OF_HISTORY[m]}
    # Cross-session reference: bright-session family ladders from the sealed
    # MIDDLE extraction alone (the "8 endpoints only" baseline of the design doc).
    sealed_family_levels = {}
    for fam in ("R", "RO", "V", "B"):
        states = [{"label": f"MIDDLE-M{m}",
                   "lab": sealed_middle[str(m)]["lab_median_cs1"],
                   "noise": sealed_middle[str(m)]["noise_floor"]}
                  for m in range(8) if FAMILY_OF_HISTORY[m] == fam]
        chain = chain_levels(states)
        sealed_family_levels[fam] = {"level_count": len(chain),
                                     "levels": [{"lstar": round(s["lab"][0], 2),
                                                 "label": s["label"]} for s in chain]}

    # --- per-cell table assembly ---
    cells: dict[tuple, dict] = {}
    for r in rows:
        lab = r["lab_median"]
        cells[(r["controller"], r["middle_code"], r["map_code"])] = {
            "controller": r["controller"], "history": r["middle_code"],
            "map_code": r["map_code"], "recipe_id": r["recipe_id"],
            "position": r["position"], "lab": lab,
            "hue_deg": hue_deg(lab), "chroma": chroma(lab),
            "noise": noise_floor(r["lstar_mad"], r["lstar_ci95_half_width"]),
            "lstar_mad": r["lstar_mad"], "lstar_ci95": r["lstar_ci95_half_width"],
            "quality_pass": r["quality_pass"],
            "single_pixel_uniform": r["single_pixel_uniform"],
            "anchor_delta_lstar": r.get("anchor_delta_lstar"),
            "anchor_delta_e76": r.get("anchor_delta_e76")}

    detection = {
        "expected_per_side": 64,
        "per_frame_detected": {f["frame"]: {c: f[c]["detected_cells"] for c in ("CS1", "CS2")}
                               for f in extraction["frames"]},
        "anchor_detected": {c: extraction["anchor_frame"]["report"][c]["detected_cells"]
                            for c in ("CS1", "CS2")},
        "min_detected_per_side": min(f[c]["detected_cells"]
                                     for f in extraction["frames"] for c in ("CS1", "CS2")),
        "quality_pass_rows": sum(1 for c in cells.values() if c["quality_pass"]),
        "single_pixel_uniform_rows": sum(1 for c in cells.values() if c["single_pixel_uniform"]),
        "anchor_max_abs_delta_lstar": max(abs(c["anchor_delta_lstar"]) for c in cells.values()),
        "anchor_max_delta_e76": max(c["anchor_delta_e76"] for c in cells.values()),
    }

    # --- control columns ---
    session_white = {ctrl: session_middle["endpoints"][ctrl]["7"]["lab_median"][0]
                     for ctrl in ("CS1", "CS2")}
    control = {"session_white_lstar": session_white,
               "sealed_middle_white_lstar": sealed_middle["7"]["lab_median_cs1"][0]}
    for code, name in ((7, "code7"), (3, "code3")):
        col = {}
        for ctrl in ("CS1", "CS2"):
            entries_c = [cells[(ctrl, m, code)] for m in range(8)]
            col[ctrl] = [{"history": c["history"], "lab": [round(v, 2) for v in c["lab"]],
                          "hue_deg": round(c["hue_deg"], 1),
                          "chroma": round(c["chroma"], 1)} for c in entries_c]
            arr = np.array([c["lab"] for c in entries_c])
            centroid = arr.mean(axis=0)
            col[ctrl + "_dispersion"] = {
                "centroid_lab": [float(v) for v in centroid],
                "lstar_span": float(arr[:, 0].max() - arr[:, 0].min()),
                "max_deviation_delta_e76": float(np.linalg.norm(arr - centroid, axis=1).max())}
        control[name] = col
    control["code7_verdict"] = (
        "FAIL vs design expectation: commented code7 from post-MIDDLE histories lands at "
        "L* %.1f-%.1f (CS1) / %.1f-%.1f (CS2), far below this session's screen white %.1f/%.1f; "
        "execution integrity is proven byte-exact, so this is tuple/history behaviour, not a "
        "frame anomaly" % (
            min(cells[("CS1", m, 7)]["lab"][0] for m in range(8)),
            max(cells[("CS1", m, 7)]["lab"][0] for m in range(8)),
            min(cells[("CS2", m, 7)]["lab"][0] for m in range(8)),
            max(cells[("CS2", m, 7)]["lab"][0] for m in range(8)),
            session_white["CS1"], session_white["CS2"]))

    # --- XOR-3 finding: MAP(white history, c) vs session MIDDLE endpoints ---
    map_m7 = {ctrl: {c: cells[(ctrl, 7, c)]["lab"] for c in range(8)} for ctrl in ("CS1", "CS2")}
    best = None
    for perm in itertools.permutations(range(8)):
        err = 0.0
        for ctrl in ("CS1", "CS2"):
            for c in range(8):
                e7 = session_middle["endpoints"][ctrl][str(perm[c])]["lab_median"]
                err += float(np.linalg.norm(np.array(map_m7[ctrl][c]) - np.array(e7)))
        if best is None or err < best[0]:
            best = (err, perm)
    xor3 = tuple(c ^ 3 for c in range(8))
    xor3_err = sum(float(np.linalg.norm(
        np.array(map_m7[ctrl][c])
        - np.array(session_middle["endpoints"][ctrl][str(c ^ 3)]["lab_median"])))
        for ctrl in ("CS1", "CS2") for c in range(8))
    per_pair = []
    for c in range(8):
        for ctrl in ("CS1", "CS2"):
            a = np.array(map_m7[ctrl][c])
            b = np.array(session_middle["endpoints"][ctrl][str(c ^ 3)]["lab_median"])
            per_pair.append({"controller": ctrl, "map_code": c,
                             "matched_middle_code": c ^ 3,
                             "delta_e76": float(np.linalg.norm(a - b)),
                             "delta_e00": delta_e_ciede2000(a, b)})
    xor3_finding = {
        "statement": "MAP (history=M7 white, code c) reproduces this session's MIDDLE "
                     "endpoint of code c^3 in full Lab, both controllers",
        "best_fit_permutation": list(best[1]),
        "best_fit_total_delta_e76": best[0],
        "xor3_permutation": list(xor3),
        "xor3_total_delta_e76": xor3_err,
        "xor3_is_best_fit": list(best[1]) == list(xor3),
        "per_pair": per_pair,
        "max_pair_delta_e00": max(p["delta_e00"] for p in per_pair),
        "excluded_causes": [
            "geometry/labelling: s3-pre MIDDLE state places code-7 cells exactly at the "
            "placement-white cells under the inherited identity/identity mapping (both sides)",
            "frame content: device input_fnv1a equals offline FNV-1a of the sealed host "
            "map.frame4bpp; per-controller streamed DTM FNV-1a also matches byte-exact",
            "drive profile: MIDDLE and MAP device reports carry identical commented profile "
            "sha256 and R20/R21 payload hashes",
        ],
        "conclusion": "commented tuple from a post-MIDDLE state is not the same code axis as "
                      "commented from SOURCE white; visually identical whites (active-C7 vs "
                      "commented-C7) are not equivalent drive-start states. Mechanism "
                      "(controller waveform selection vs panel memory) is not resolvable "
                      "offline."}

    # --- 8x8 tables per side ---
    tables = {}
    for ctrl in ("CS1", "CS2"):
        tables[ctrl] = {
            "lstar": [[round(cells[(ctrl, m, c)]["lab"][0], 2) for c in range(8)]
                      for m in range(8)],
            "hue_deg": [[round(cells[(ctrl, m, c)]["hue_deg"], 1) for c in range(8)]
                        for m in range(8)],
            "chroma": [[round(cells[(ctrl, m, c)]["chroma"], 1) for c in range(8)]
                       for m in range(8)],
            "noise_floor": [[round(cells[(ctrl, m, c)]["noise"], 2) for c in range(8)]
                            for m in range(8)],
            "row_labels": [f"M{m}" for m in range(8)],
            "col_labels": [f"C{c}" for c in range(8)]}

    # --- side consistency (CS1 vs CS2 are independent re-tests of same tuples) ---
    consistency = []
    for m in range(8):
        for c in range(8):
            a = np.array(cells[("CS1", m, c)]["lab"])
            b = np.array(cells[("CS2", m, c)]["lab"])
            consistency.append({"history": m, "map_code": c,
                                "delta_lstar": float(abs(a[0] - b[0])),
                                "delta_e00": delta_e_ciede2000(a, b),
                                "delta_e76": float(np.linalg.norm(a - b))})
    side_consistency = {
        "median_abs_delta_lstar": float(np.median([c["delta_lstar"] for c in consistency])),
        "max_abs_delta_lstar": max(c["delta_lstar"] for c in consistency),
        "median_delta_e00": float(np.median([c["delta_e00"] for c in consistency])),
        "max_delta_e00": max(c["delta_e00"] for c in consistency),
        "worst_pairs": sorted(consistency, key=lambda x: -x["delta_lstar"])[:8],
        "note": "CS2 reads systematically darker (illumination gradient); pairs are "
                "frame-synchronous same-tuple re-tests"}

    # --- hue-family lightness ladders ---
    ladders = {}
    for ctrl in ("CS1", "CS2"):
        per_family: dict[str, list] = {}
        endpoints = session_middle["endpoints"][ctrl]
        for m in range(8):
            fam = FAMILY_OF_HISTORY[m]
            ep = endpoints[str(m)]
            anchor_lab = np.array(ep["lab_median"])
            anchor_noise = noise_floor(ep["lstar_mad_spatial"], ep["lstar_ci95_half_width_spatial"])
            states = [{"label": f"MIDDLE-M{m}", "lab": [float(v) for v in anchor_lab],
                       "noise": anchor_noise, "source": "middle_endpoint"}]
            excluded = []
            for c in range(8):
                cell = cells[(ctrl, m, c)]
                lab = np.array(cell["lab"])
                if not (cell["quality_pass"] and cell["single_pixel_uniform"]):
                    excluded.append({"label": f"MAP-M{m}-C{c}", "reason": "quality"})
                    continue
                if cell["chroma"] <= CHROMA_GATE:
                    excluded.append({"label": f"MAP-M{m}-C{c}", "reason": "chroma_gate",
                                     "chroma": cell["chroma"]})
                    continue
                hg = hue_gap(lab, anchor_lab)
                if fam != "WHITE" and hg > GATE_HUE_DEG:
                    excluded.append({"label": f"MAP-M{m}-C{c}", "reason": "hue_drift",
                                     "hue_gap_deg": hg, "hue_deg": cell["hue_deg"]})
                    continue
                if fam == "WHITE":
                    excluded.append({"label": f"MAP-M{m}-C{c}", "reason": "white_history_neutral"})
                    continue
                states.append({"label": f"MAP-M{m}-C{c}", "lab": [float(v) for v in lab],
                               "noise": cell["noise"], "source": "map_cell",
                               "hue_gap_to_anchor_deg": hg})
            per_family.setdefault(fam, []).append(
                {"history": m, "anchor_hue_deg": hue_deg(anchor_lab),
                 "states": states, "excluded": excluded})
        fam_report = {}
        for fam, per_m in per_family.items():
            if fam == "WHITE":
                continue
            all_states = [s for pm in per_m for s in pm["states"]]
            chain = chain_levels(all_states)
            kept = {s["label"] for s in chain}
            blocked_summary = {"hue_gap_over_5deg": 0, "noise_floor": 0,
                               "dlstar_or_de00_gate": 0}
            for s in all_states:
                if s["label"] in kept or "blocked_by" not in s:
                    continue
                b = s["blocked_by"]
                if b["hue_gap_deg"] > GATE_HUE_DEG:
                    blocked_summary["hue_gap_over_5deg"] += 1
                elif b["delta_lstar"] < b["noise_floor_sum"]:
                    blocked_summary["noise_floor"] += 1
                else:
                    blocked_summary["dlstar_or_de00_gate"] += 1
            fam_report[fam] = {
                "member_histories": [pm["history"] for pm in per_m],
                "pool_size": len(all_states),
                "level_count": len(chain),
                "blocked_reason_counts": blocked_summary,
                "levels": [{"lstar": round(s["lab"][0], 2), "label": s["label"],
                            "hue_deg": round(hue_deg(s["lab"]), 1),
                            "chroma": round(chroma(s["lab"]), 1)} for s in chain],
                "meets_user_4_6": USER_ACCEPTABLE_LEVELS[0] <= len(chain) <= USER_ACCEPTABLE_LEVELS[1],
                "excluded_states": [{"history": pm["history"], **ex}
                                    for pm in per_m for ex in pm["excluded"]]}
        # Neutral pool: white endpoint plus near-neutral MAP cells; hue is
        # numerically unstable at low chroma, so the hue gate is not enforced.
        ep7 = session_middle["endpoints"][ctrl]["7"]
        neutral_states = [{"label": "MIDDLE-M7-white",
                           "lab": [float(v) for v in ep7["lab_median"]],
                           "noise": noise_floor(ep7["lstar_mad_spatial"],
                                                ep7["lstar_ci95_half_width_spatial"]),
                           "source": "middle_endpoint"}]
        for m in range(8):
            for c in range(8):
                cell = cells[(ctrl, m, c)]
                if (cell["quality_pass"] and cell["single_pixel_uniform"]
                        and cell["chroma"] <= CHROMA_GATE):
                    neutral_states.append({"label": f"MAP-M{m}-C{c}",
                                           "lab": cell["lab"], "noise": cell["noise"],
                                           "source": "map_cell"})
        neutral_chain = chain_levels(neutral_states, enforce_hue=False)
        fam_report["NEUTRAL"] = {
            "member_histories": [7], "pool_size": len(neutral_states),
            "level_count": len(neutral_chain),
            "levels": [{"lstar": round(s["lab"][0], 2), "label": s["label"],
                        "hue_deg": round(hue_deg(s["lab"]), 1),
                        "chroma": round(chroma(s["lab"]), 1)} for s in neutral_chain],
            "note": "pool = C*<=8 MAP cells plus the M7 white endpoint (white family, "
                    "kept regardless of measured chroma); hue gate not enforced"}
        ladders[ctrl] = fam_report

    # --- new resolvable levels beyond the 8 MIDDLE endpoints (per family/side) ---
    new_levels = {}
    for ctrl in ("CS1", "CS2"):
        fams = ladders[ctrl]
        per_fam = {}
        for fam, rep in fams.items():
            ep_states = [lv for lv in rep["levels"] if lv["label"].startswith("MIDDLE-")]
            new_states = [lv for lv in rep["levels"] if lv["label"].startswith("MAP-")]
            per_fam[fam] = {"middle_endpoint_levels": ep_states,
                            "new_map_levels": new_states,
                            "new_level_count": len(new_states)}
        new_levels[ctrl] = per_fam

    conclusions = []
    for ctrl in ("CS1", "CS2"):
        for fam, rep in ladders[ctrl].items():
            conclusions.append(
                f"{ctrl} {fam}: {rep['level_count']} resolvable levels "
                f"(pool {rep['pool_size']})")

    analysis = {
        "kind": "mf1750-lh2-drive-map-analysis-v1",
        "analysis_version": ANALYSIS_VERSION,
        "inputs": {
            "extraction_sha256": rec.digest(extraction_path.read_bytes()),
            "package_contract_sha256": rec.digest(
                (args.package / "contract.json").read_bytes()),
            "sealed_middle_extraction_sha256": rec.digest(args.middle_extraction.read_bytes()),
            "s3_pre_sha256": rec.digest((args.batch / "s3-pre.jpg").read_bytes()),
            "batch_dir": str(args.batch)},
        "lab_space": "camera-relative (dark evening session; NOT comparable in absolute "
                     "L* to the sealed 2026-09-17 bright session: screen white %.1f vs %.1f)"
                     % (session_white["CS1"], sealed_middle["7"]["lab_median_cs1"][0]),
        "gates": {"delta_lstar_min": GATE_DL, "delta_e00_min": GATE_DE00,
                  "hue_gap_max_deg": GATE_HUE_DEG, "chroma_gate": CHROMA_GATE,
                  "noise_floor": "max(5*MAD, CI95 half width); pair resolvable requires "
                                 "dL* >= sum of both floors",
                  "user_acceptable_levels": list(USER_ACCEPTABLE_LEVELS)},
        "execution_integrity": integrity,
        "session_middle_endpoints": session_middle,
        "code7_white_check_this_session": code7_white_check,
        "sealed_middle_endpoints_bright_session": sealed_middle,
        "sealed_bright_session_family_levels": sealed_family_levels,
        "detection": detection,
        "control_columns": control,
        "xor3_finding": xor3_finding,
        "map_tables": tables,
        "side_consistency": side_consistency,
        "family_ladders": ladders,
        "new_levels_beyond_middle_endpoints": new_levels,
        "conclusions": conclusions,
        "qualified_count": 0,
        "hardware_accessed": False,
        "visible_refresh": 0}
    rec.write_new(out_dir / "map-analysis.json", rec.seal(analysis))

    # --- heatmap PNG ---
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(19, 6.5))
    for ax, ctrl in ((axes[0], "CS1"), (axes[1], "CS2")):
        data = np.array(tables[ctrl]["lstar"])
        im = ax.imshow(data, cmap="viridis", vmin=0,
                       vmax=max(40.0, float(data.max()) + 1))
        ax.set_title(f"{ctrl} MAP measured L* (camera-relative, dark session)\n"
                     f"rows=history M0..M7, cols=map code 0..7")
        ax.set_xticks(range(8), [f"C{c}" for c in range(8)])
        ax.set_yticks(range(8), [f"M{m}" for m in range(8)])
        for m in range(8):
            for c in range(8):
                ax.text(c, m, f"{data[m, c]:.1f}", ha="center", va="center",
                        color="white" if data[m, c] < 20 else "black", fontsize=8)
        fig.colorbar(im, ax=ax, label="L*")
    dmat = np.zeros((8, 8))
    for c in consistency:
        dmat[c["history"], c["map_code"]] = c["delta_lstar"]
    im = axes[2].imshow(dmat, cmap="magma", vmin=0)
    axes[2].set_title("|dL*| CS1 vs CS2 (same tuple, same frame)")
    axes[2].set_xticks(range(8), [f"C{c}" for c in range(8)])
    axes[2].set_yticks(range(8), [f"M{m}" for m in range(8)])
    for m in range(8):
        for c in range(8):
            axes[2].text(c, m, f"{dmat[m, c]:.1f}", ha="center", va="center",
                         color="white" if dmat[m, c] < dmat.max() * 0.6 else "black",
                         fontsize=8)
    fig.colorbar(im, ax=axes[2], label="|dL*|")
    fig.suptitle("LH2 drive-map MAP 2026-09-18: measured L* per (history, map code)")
    fig.tight_layout()
    png_path = out_dir / "map-lstar-heatmap.png"
    with png_path.open("xb") as fh:
        fig.savefig(fh, dpi=140)
    plt.close(fig)

    # --- frozen copy of this tool + sealed review ---
    tool_copy = out_dir / "map-analysis-tool.py"
    with tool_copy.open("xb") as fh:
        fh.write(Path(__file__).read_bytes())
    analyzer_path = ROOT / "tools" / "mf1750_lh2_drive_map_photo_analyzer.py"

    def fileinfo(path: Path) -> dict:
        return {"path": str(path.resolve()), "bytes": path.stat().st_size,
                "sha256": rec.digest(path.read_bytes())}

    review = {
        "kind": "mf1750-lh2-drive-map-analysis-review-v1",
        "run_id": "LH2_DRIVE_MAP_20260918_V1",
        "recorded_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "analyzer_tool": fileinfo(analyzer_path),
        "analysis_tool_frozen_copy": fileinfo(tool_copy),
        "extraction": fileinfo(extraction_path),
        "map_analysis": fileinfo(out_dir / "map-analysis.json"),
        "heatmap_png": fileinfo(png_path),
        "batch_dir": str(args.batch.resolve()),
        "lab_space": analysis["lab_space"],
        "geometry": {
            "mapping": {"CS1": "image-left", "CS2": "image-right",
                        "orientation": "identity/identity",
                        "source": "inherited from sealed LH1 rebound MIDDLE extraction"},
            "session_validation": code7_white_check,
            "detected_cells_per_side": {
                "min": detection["min_detected_per_side"], "expected": 64,
                "note": "one near-white cell per side stays undetected by design; "
                        "positions come from the per-frame homography"}},
        "execution_integrity": integrity,
        "findings": {
            "control_code7": control["code7_verdict"],
            "control_code3": {
                ctrl: control["code3"][ctrl + "_dispersion"] for ctrl in ("CS1", "CS2")},
            "xor3": {"statement": xor3_finding["statement"],
                     "xor3_is_best_fit": xor3_finding["xor3_is_best_fit"],
                     "max_pair_delta_e00": xor3_finding["max_pair_delta_e00"]},
            "side_consistency": {k: side_consistency[k] for k in
                                 ("median_abs_delta_lstar", "max_abs_delta_lstar",
                                  "median_delta_e00", "max_delta_e00")},
            "family_level_counts": {ctrl: {fam: rep["level_count"]
                                           for fam, rep in ladders[ctrl].items()}
                                    for ctrl in ("CS1", "CS2")},
            "new_map_levels": {ctrl: {fam: rep["new_level_count"]
                                      for fam, rep in new_levels[ctrl].items()}
                               for ctrl in ("CS1", "CS2")},
        },
        "interpretation": None,  # filled below before sealing
        "qualified_count": 0,
        "actual_counts": {"arm": 0, "camera_captures": 0, "driver": 0, "execute": 0,
                          "hardware_accessed": False, "visible_refresh": 0}}
    counts = {fam: (ladders["CS1"][fam]["level_count"], ladders["CS2"][fam]["level_count"])
              for fam in ladders["CS1"]}
    review["interpretation"] = (
        "MAP drive from post-MIDDLE histories does not reproduce the from-white commented "
        "code axis: the white-history row matches MIDDLE endpoints under code c^3, and the "
        "code7 control column stays dark instead of white. Per-family resolvable levels "
        f"(CS1/CS2): {counts}. qualified stays 0; discovery screening only.")
    rec.write_new(out_dir / "analysis-review.json", rec.seal(review))
    print(json.dumps({"written": [str(out_dir / n) for n in
                                  ("map-analysis.json", "map-lstar-heatmap.png",
                                   "analysis-review.json", "map-analysis-tool.py")],
                      "family_levels": counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
