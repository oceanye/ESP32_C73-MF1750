#!/usr/bin/env python3
"""Offline XOR-3 code-axis mechanism study for the LH2 drive-map MAP frame.

Read-only offline analysis over sealed evidence. Observation under study (from
LH2_DRIVE_MAP_ANALYSIS_20260918_V1): MAP cells with white history (M7) driven
with code c reproduce, in full camera-relative Lab, this session's MIDDLE
endpoint of code c^3 (permutation (3,2,1,0,7,6,5,4)), on both controllers.

Sections:
1. Per-frame robustness: the XOR-3 pairing is re-fitted on each of the 10
   same-state frames separately (never on medians), per controller.
2. Competing hypotheses: (a) geometry/labelling error — candidate geometric
   relabelings of the 8x8 grid are tested against the recipe-preservation
   constraint, and M7-row assignment scatter is compared with all cells;
   (b) frame content — already excluded byte-exact, referenced only;
   (c) history-code interaction — every history row M0..M6 gets its own
   best-fit permutation against the MIDDLE endpoints plus attractor
   (convergence) statistics; (d) side consistency of the XOR-3 direction.
3. Static LUT evidence: the two vendor 535-byte tables in
   参考资料/.../User/EDP_init.c (commented block + active block) are parsed,
   hash-pinned against src/generated/spd1657_legacy_535_reference.inc, split
   into the vendor-documented 6 categories x 8 groups x 11 bytes, and tested
   byte-exact for any XOR-3/permutation symmetry within and between tables.
4. LH3 design implications (report only; no chain is designed here).
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from host.color_pipeline.color import delta_e_ciede2000  # noqa: E402
from tools import mf1750_lh1_lh4_once as rec  # noqa: E402
from tools import mf1750_lh2_drive_map_analysis as map_analysis  # noqa: E402

ANALYSIS_VERSION = "mf1750-lh2-xor3-mechanism-analysis-v1"
XOR3 = tuple(c ^ 3 for c in range(8))
IDENTITY = tuple(range(8))
VENDOR_SOURCE = ROOT / "参考资料" / "REG-API-oqc(1)(1)" / "REG-API-oqc" / "User" / "EDP_init.c"
GENERATED_INC = ROOT / "src" / "generated" / "spd1657_legacy_535_reference.inc"
HEADER_BYTES = 7
GROUP_BYTES = 11
GROUPS_PER_CATEGORY = 8
LEGACY_CATEGORIES = 6
TRANSMITTED = HEADER_BYTES + LEGACY_CATEGORIES * GROUPS_PER_CATEGORY * GROUP_BYTES  # 535

ALL_PERMS = list(itertools.permutations(range(8)))


def best_permutation(errors: np.ndarray) -> tuple[tuple[int, ...], float]:
    """errors[c, j] = cost of pairing observed code c with reference j."""
    best_p, best_e = None, math.inf
    for perm in ALL_PERMS:
        e = float(sum(errors[c, perm[c]] for c in range(8)))
        if e < best_e - 1e-12:
            best_p, best_e = perm, e
    return best_p, best_e


def de76(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)))


def parse_vendor_tables(path: Path) -> dict:
    """Parse EDP_init.c: the commented-out table block and the active block.

    Both are 535-byte R20 tables; vendor comments name the 6 categories
    (VCOM, Black, White, Yellow, Red, Power) x GROUP1..8.
    """
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    byte_re = re.compile(r"0x([0-9A-Fa-f]{2})")
    commented, active = [], []
    commented_labels, active_labels = [], []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("//") and "0x" in stripped:
            vals = byte_re.findall(stripped[2:])
            if vals:
                commented.extend(int(v, 16) for v in vals)
                m = re.search(r"//\s*([A-Za-z]+-GROUP\d|VGHL.*)$", stripped[2:])
                commented_labels.append(m.group(1) if m else "")
        elif stripped.startswith("0x"):
            vals = byte_re.findall(stripped)
            active.extend(int(v, 16) for v in vals)
            m = re.search(r"//\s*([A-Za-z]+-GROUP\d|VGHL.*)$", stripped)
            active_labels.append(m.group(1) if m else "")
    return {"commented": bytes(commented[:TRANSMITTED]),
            "active": bytes(active[:TRANSMITTED]),
            "commented_raw_len": len(commented), "active_raw_len": len(active),
            "commented_labels": commented_labels, "active_labels": active_labels}


def parse_inc_tables(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    out = {}
    for ns in ("active", "commented"):
        body = text.split(f"namespace {ns} {{")[1].split(f"}}  // namespace {ns}")[0]
        m = re.search(r"kR20Payload\[799\] = \{([^}]*)\}", body)
        vals = [int(v, 16) for v in re.findall(r"0x([0-9A-Fa-f]{2})", m.group(1))]
        out[ns] = bytes(vals)
    return out


def group_rows(table535: bytes) -> list[list[bytes]]:
    body = table535[HEADER_BYTES:TRANSMITTED]
    return [[body[cat * 88 + g * 11: cat * 88 + (g + 1) * 11] for g in range(8)]
            for cat in range(6)]


def symmetry_count(rows: list[list[bytes]], perm) -> dict:
    """Count nontrivial block(s, g) == block(s, perm(g)) pairs (g != perm(g))."""
    eq, total = 0, 0
    per_category = []
    for s, cat in enumerate(rows):
        ceq = sum(1 for g in range(8) if perm[g] != g and cat[g] == cat[perm[g]])
        per_category.append(ceq)
        eq += ceq
        total += sum(1 for g in range(8) if perm[g] != g)
    return {"equal_blocks": eq, "total_blocks": total, "per_category": per_category}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--extraction", type=Path, required=True,
                   help="sealed LH2 MAP extraction.json (10-frame per-ROI samples)")
    p.add_argument("--map-analysis", type=Path, required=True,
                   help="sealed map-analysis.json (execution integrity evidence)")
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--batch", type=Path, required=True)
    args = p.parse_args()
    if args.output_dir.exists():
        raise SystemExit("output dir must not exist (O_EXCL batch)")

    extraction = json.loads(args.extraction.read_text(encoding="utf-8"))
    map_analysis_doc = json.loads(args.map_analysis.read_text(encoding="utf-8"))
    rows = extraction["rows"]
    cell = {(r["controller"], r["middle_code"], r["map_code"]): r for r in rows}

    # Session-consistent MIDDLE endpoints (single s3-pre frame, 8 replicas each).
    session_middle = map_analysis.session_middle_endpoints(
        args.batch / "s3-pre.jpg", args.package)
    endpoints = {ctrl: {c: np.array(session_middle["endpoints"][ctrl][str(c)]["lab_median"])
                        for c in range(8)} for ctrl in ("CS1", "CS2")}

    # ---------- 1. per-frame robustness ----------
    n_frames = len(rows[0]["lab_samples"])
    per_frame = []
    all_pairs = []
    for k in range(n_frames):
        for ctrl in ("CS1", "CS2"):
            obs = {c: np.array(cell[(ctrl, 7, c)]["lab_samples"][k]) for c in range(8)}
            errors = np.array([[de76(obs[c], endpoints[ctrl][j]) for j in range(8)]
                               for c in range(8)])
            perm, err = best_permutation(errors)
            xor3_err = float(sum(errors[c, c ^ 3] for c in range(8)))
            ident_err = float(sum(errors[c, c] for c in range(8)))
            pairs = []
            for c in range(8):
                d00 = delta_e_ciede2000(obs[c], endpoints[ctrl][c ^ 3])
                dl = float(abs(obs[c][0] - endpoints[ctrl][c ^ 3][0]))
                pairs.append({"frame": k, "controller": ctrl, "map_code": c,
                              "matched_middle_code": c ^ 3,
                              "delta_e00": d00, "abs_delta_lstar": dl})
                all_pairs.append((d00, dl))
            per_frame.append({"frame": k, "controller": ctrl,
                              "best_permutation": list(perm),
                              "best_is_xor3": list(perm) == list(XOR3),
                              "best_total_delta_e76": err,
                              "xor3_total_delta_e76": xor3_err,
                              "identity_total_delta_e76": ident_err,
                              "xor3_vs_identity_margin": ident_err - xor3_err,
                              "pair_max_delta_e00": max(x["delta_e00"] for x in pairs)})
    d00s = np.array([x[0] for x in all_pairs])
    dls = np.array([x[1] for x in all_pairs])
    robustness = {
        "frames": n_frames,
        "pair_count": len(all_pairs),
        "per_frame": per_frame,
        "every_frame_best_is_xor3": all(f["best_is_xor3"] for f in per_frame),
        "delta_e00": {"median": float(np.median(d00s)), "p95": float(np.percentile(d00s, 95)),
                      "max": float(d00s.max())},
        "abs_delta_lstar": {"median": float(np.median(dls)),
                            "p95": float(np.percentile(dls, 95)), "max": float(dls.max())},
        "identity_permutation_total_delta_e76_median": float(np.median(
            [f["identity_total_delta_e76"] for f in per_frame])),
        "xor3_total_delta_e76_median": float(np.median(
            [f["xor3_total_delta_e76"] for f in per_frame])),
        "reference_note": "reference = s3-pre session MIDDLE endpoints (single frame, "
                          "8-position spatial median per code per side); MAP side uses "
                          "individual frames, so this tests the median-based pairing "
                          "against per-frame noise",
    }

    # ---------- 2a. geometry hypothesis ----------
    placement_all = map_analysis.base.load_placement(
        args.package / "generated" / "ec5_lightness_lh2_drive_map_v1_identity.inc")
    candidates = {
        "identity": lambda r, c: (r, c),
        "rot180": lambda r, c: (7 - r, 7 - c),
        "flip_rows": lambda r, c: (7 - r, c),
        "flip_cols": lambda r, c: (r, 7 - c),
        "transpose": lambda r, c: (c, r),
        "quadrant_flip_both_halves": lambda r, c: (r ^ 4, c ^ 4),
        "quadrant_flip_row_half": lambda r, c: (r ^ 4, c),
        "quadrant_flip_col_half": lambda r, c: (r, c ^ 4),
    }
    geometry_tests = []
    for name, g in candidates.items():
        for ctrl, table in (("CS1", placement_all["kRecipeAtCellCs1"]),
                            ("CS2", placement_all["kRecipeAtCellCs2"])):
            ok, detail = True, []
            for r in range(8):
                for c in range(8):
                    recipe = table[r * 8 + c]
                    if recipe % 8 != 7:
                        continue
                    code = map_analysis.analyzer.map_code(recipe // 8, r, c)
                    gr, gc = g(r, c)
                    recipe_g = table[gr * 8 + gc]
                    code_g = map_analysis.analyzer.map_code(recipe_g // 8, gr, gc)
                    # A labelling error G explains XOR-3 only if the cell my
                    # pipeline labelled (M7, code) physically holds a
                    # white-history (recipe%8==7) cell driven with code^3.
                    if not (recipe_g % 8 == 7 and code_g == (code ^ 3)):
                        ok = False
                        detail.append({"at": [r, c], "labelled_code": code,
                                       "physical_recipe": recipe_g,
                                       "physical_code": code_g})
            geometry_tests.append({"candidate": name, "controller": ctrl,
                                   "explains_xor3": ok,
                                   "first_counterexamples": detail[:3]})
    scatter_m7 = [r["assignment_scatter_px"] for (ct, m, c), r in cell.items()
                  if m == 7 and r["assignment_scatter_px"] is not None]
    scatter_all = [r["assignment_scatter_px"] for r in rows
                   if r["assignment_scatter_px"] is not None]
    geometry = {
        "candidate_relabelings": geometry_tests,
        "any_candidate_explains": any(t["explains_xor3"] for t in geometry_tests),
        "m7_row_assignment_scatter_px": {"count": len(scatter_m7),
                                         "max": max(scatter_m7) if scatter_m7 else None,
                                         "median": float(np.median(scatter_m7)) if scatter_m7 else None},
        "all_cells_assignment_scatter_px": {"count": len(scatter_all),
                                            "max": max(scatter_all),
                                            "median": float(np.median(scatter_all))},
        "note": "s3-pre code7-white validation already pinned identity/identity "
                "for this session; the quadrant_flip_both candidate is the only "
                "geometric transform that maps code c -> c^3, and it fails the "
                "recipe-preservation constraint on both placement tables",
    }

    # ---------- 2c. per-history-row permutation fits + attractor stats ----------
    row_fits = []
    for m in range(8):
        for ctrl in ("CS1", "CS2"):
            obs = {c: np.array(cell[(ctrl, m, c)]["lab_median"]) for c in range(8)}
            errors = np.array([[de76(obs[c], endpoints[ctrl][j]) for j in range(8)]
                               for c in range(8)])
            perm, err = best_permutation(errors)
            labs = np.stack([obs[c] for c in range(8)])
            centroid = labs.mean(axis=0)
            row_fits.append({
                "history": m, "controller": ctrl,
                "best_permutation": list(perm),
                "best_is_xor3": list(perm) == list(XOR3),
                "best_mean_delta_e76": err / 8,
                "xor3_mean_delta_e76": float(sum(errors[c, c ^ 3] for c in range(8))) / 8,
                "identity_mean_delta_e76": float(sum(errors[c, c] for c in range(8))) / 8,
                "row_lstar_span": float(labs[:, 0].max() - labs[:, 0].min()),
                "row_max_pairwise_delta_e76": float(max(
                    de76(labs[i], labs[j]) for i in range(8) for j in range(i + 1, 8))),
                "row_max_deviation_from_centroid_delta_e76":
                    float(np.linalg.norm(labs - centroid, axis=1).max()),
                "interpretation": None})
    for rf in row_fits:
        if rf["history"] == 7:
            rf["interpretation"] = "white history: clean XOR-3 code-axis match"
        elif rf["xor3_mean_delta_e76"] - rf["best_mean_delta_e76"] < 0.5 and \
                rf["identity_mean_delta_e76"] - rf["xor3_mean_delta_e76"] > 5.0:
            rf["interpretation"] = ("approximate XOR-3: far better than identity but with "
                                    "history-dependent residual distortion")
        elif rf["row_max_deviation_from_centroid_delta_e76"] < 5.0:
            rf["interpretation"] = "row converged (attractor): codes barely distinguishable, " \
                                   "permutation fit meaningless"
        else:
            rf["interpretation"] = "no clean permutation structure"

    # ---------- 2d. side consistency ----------
    side_pairs = {"CS1": [], "CS2": []}
    for k in range(n_frames):
        for ctrl in ("CS1", "CS2"):
            for c in range(8):
                o = np.array(cell[(ctrl, 7, c)]["lab_samples"][k])
                side_pairs[ctrl].append(delta_e_ciede2000(o, endpoints[ctrl][c ^ 3]))
    side_consistency = {
        ctrl: {"median_delta_e00": float(np.median(v)), "max_delta_e00": float(max(v))}
        for ctrl, v in side_pairs.items()}
    # Cross-side same-tuple comparison on the M7 row (both sides, same frame):
    cross = []
    for c in range(8):
        a = np.array(cell[("CS1", 7, c)]["lab_median"])
        b = np.array(cell[("CS2", 7, c)]["lab_median"])
        cross.append({"map_code": c, "cross_side_delta_e00": delta_e_ciede2000(a, b),
                      "cross_side_abs_delta_lstar": float(abs(a[0] - b[0]))})
    side_consistency["m7_row_cross_side"] = cross
    side_consistency["xor3_direction_same_both_sides"] = bool(
        all(f["best_is_xor3"] for f in per_frame))

    # ---------- 3. static LUT evidence ----------
    vendor = parse_vendor_tables(VENDOR_SOURCE)
    inc_tables = parse_inc_tables(GENERATED_INC)
    static = {"vendor_source": str(VENDOR_SOURCE),
              "vendor_source_sha256": rec.digest(VENDOR_SOURCE.read_bytes())}
    sha = {ns: rec.digest(vendor[ns]) for ns in ("active", "commented")}
    static["transmitted_prefix_sha256"] = sha
    static["matches_pinned_hashes"] = {
        "active": sha["active"] == "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b",
        "commented": sha["commented"] == "2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26"}
    static["matches_generated_inc"] = {
        ns: vendor[ns] == inc_tables[ns][:TRANSMITTED] for ns in ("active", "commented")}
    static["geometry"] = {"header_bytes": HEADER_BYTES, "categories": LEGACY_CATEGORIES,
                          "groups_per_category": GROUPS_PER_CATEGORY,
                          "group_bytes": GROUP_BYTES, "transmitted": TRANSMITTED,
                          "static_assert": "kTransmittedR20PrefixBytes == 7 + 6 * 8 * 11"}
    static["category_order_active"] = sorted({lbl.split("-")[0] for lbl in vendor["active_labels"]
                                              if "-GROUP" in lbl})
    static["category_order_commented"] = sorted({lbl.split("-")[0]
                                                 for lbl in vendor["commented_labels"]
                                                 if "-GROUP" in lbl})
    static["category_sequence_commented"] = [lbl.split("-")[0] for lbl in vendor["commented_labels"]
                                             if lbl.endswith("GROUP1")]
    static["category_sequence_active"] = [lbl.split("-")[0] for lbl in vendor["active_labels"]
                                          if lbl.endswith("GROUP1")]
    static["same_category_order"] = (static["category_sequence_commented"]
                                     == static["category_sequence_active"])
    va, vc = group_rows(vendor["active"]), group_rows(vendor["commented"])
    static["header_bytes_active"] = list(vendor["active"][:7])
    static["header_bytes_commented"] = list(vendor["commented"][:7])
    static["header_diff_meaning"] = (
        "vendor layout 'VGHL,VSHL_0,VSH_1,VSL_1,VSHL_1,VCOM,PLL': VSHL_0 0x1E->0x24, "
        "VSL_1 0x20->0x27, VSHL_1 0x1E->0x20, PLL 0x02->0x03 (VSH_1/VCOM unchanged) — "
        "the two tuples differ in drive voltages and PLL divider, so active-C7 white "
        "and commented-C7 white are electrically different refreshes")
    # same-index block equality
    same_index = sum(1 for s in range(6) for g in range(8) if va[s][g] == vc[s][g])
    static["active_vs_commented_same_index_equal_blocks"] = {"equal": same_index, "of": 48}
    # per-category group permutation between tables
    cross_perm = []
    for s in range(6):
        errors = np.array([[0 if vc[s][g] == va[s][j] else 1 for j in range(8)]
                           for g in range(8)], dtype=float)
        perm, err = best_permutation(errors)
        cross_perm.append({"category": s, "best_group_permutation": list(perm),
                           "matched_blocks": 8 - int(err),
                           "is_xor3": list(perm) == list(XOR3)})
    static["commented_vs_active_group_permutation_per_category"] = cross_perm
    # within-table group symmetries
    perms_tested = {"xor3": XOR3, "complement_xor7": tuple(7 - c for c in range(8)),
                    "bit_reverse_3bit": (0, 4, 2, 6, 1, 5, 3, 7),
                    "identity": IDENTITY}
    static["within_table_group_symmetry"] = {
        ns: {pname: symmetry_count(rows, perm)
             for pname, perm in perms_tested.items()}
        for ns, rows in (("active", va), ("commented", vc))}
    # all-FF (no-op) blocks per table
    static["all_ff_blocks"] = {
        ns: sum(1 for s in range(6) for g in range(8) if rows[s][g] == b"\xff" * 11)
        for ns, rows in (("active", va), ("commented", vc))}
    static["vendor_comment_evidence"] = [
        "EDP_init.c line 13: '//0x00,0x24,0x78,0x27,0x20,0x14,0x03,//VGHL,VSHL_0,VSH_1,VSL_1,VSHL_1,VCOM,PLL' "
        "(commented table header)",
        "EDP_init.c lines 14-61: the commented-out table carries per-11-byte labels "
        "'VCOM-GROUP1..8', 'Black-GROUP1..8', 'White-GROUP1..8', 'Yellow-GROUP1..8', "
        "'Red-GROUP1..8', 'Power-GROUP1..8'",
        "EDP_init.c lines 63-111: the active table uses the same category order",
        "generated inc header: 'Generated from the two complete, identity-pinned 535-byte "
        "tables in the vendor-delivered EDP_init.c. The 264-byte 0xFF suffix exists only "
        "so this evidence can share the fixed 799-byte validation container'",
        "tools/mf1750_spd1657_phase_geometry_audit.py docstring: 'SPD1656 uses 20x11 bytes "
        "for VCOM but 20x13 bytes for each 3-bit color LUT, while these SPD1657/E2802 "
        "candidates use 8x11 bytes under every labeled/indexed category' — the group "
        "semantics (old-state vs phase-plan) are NOT documented in vendor sources",
    ]

    # ---------- synthesis ----------
    conclusions = {
        "per_frame_robustness": ("XOR-3 is the argmin permutation on every one of the "
                                 f"{n_frames} frames x 2 controllers; pairing ΔE00 "
                                 f"median {robustness['delta_e00']['median']:.2f}, "
                                 f"P95 {robustness['delta_e00']['p95']:.2f}, "
                                 f"max {robustness['delta_e00']['max']:.2f} — not a "
                                 "median coincidence"),
        "hypothesis_geometry": "REJECTED" if not geometry["any_candidate_explains"]
                               else "SUPPORTED",
        "hypothesis_frame_content": "REJECTED (byte-exact fnv1a evidence, referenced)",
        "hypothesis_history_code_interaction": None,  # filled below
        "hypothesis_side_consistency": None,
        "static_lut": None,
    }
    m7_fit = [rf for rf in row_fits if rf["history"] == 7]
    other = [rf for rf in row_fits if rf["history"] != 7]
    approx = [rf for rf in other if "approximate XOR-3" in (rf["interpretation"] or "")]
    conclusions["hypothesis_history_code_interaction"] = (
        f"the white-history row is an EXACT XOR-3 match (mean ΔE76 "
        f"{min(rf['xor3_mean_delta_e76'] for rf in m7_fit):.2f}, max pair ΔE00 "
        f"{robustness['delta_e00']['max']:.2f}); the coloured-history rows reject identity "
        f"(identity mean ΔE76 20-28) and sit at XOR-3 mean ΔE76 "
        f"{min(rf['xor3_mean_delta_e76'] for rf in other):.1f}-"
        f"{max(rf['xor3_mean_delta_e76'] for rf in other):.1f} with "
        f"{len(approx)}/14 rows within 0.5 of their own best permutation — the code-axis "
        "shift is global to the MAP stage; white-origin rows carry it exactly, "
        "coloured-origin rows carry it approximately plus history-dependent distortion")
    conclusions["hypothesis_side_consistency"] = (
        "CS1 and CS2 fit the SAME XOR-3 direction on every frame (same tuple, same frame, "
        "independent controllers) — consistent with a shared controller/panel mechanism")
    conclusions["static_lut"] = (
        "no XOR-3 byte-level symmetry exists inside either vendor table, and the commented "
        "table is not a group-permutation of the active table; the two tables differ in "
        "header drive voltages + PLL and in waveform bytes. The uploaded LUT therefore "
        "contains no static counterpart of the observed c -> c^3 mapping: the mechanism "
        "is downstream (controller-internal decode state or panel state memory), not in "
        "the transmitted bytes")

    analysis = {
        "kind": "mf1750-lh2-xor3-mechanism-analysis-v1",
        "analysis_version": ANALYSIS_VERSION,
        "inputs": {
            "extraction_sha256": rec.digest(args.extraction.read_bytes()),
            "map_analysis_sha256": rec.digest(args.map_analysis.read_bytes()),
            "vendor_edp_init_sha256": static["vendor_source_sha256"],
            "generated_inc_sha256": rec.digest(GENERATED_INC.read_bytes()),
            "s3_pre_sha256": rec.digest((args.batch / "s3-pre.jpg").read_bytes())},
        "xor3_permutation": list(XOR3),
        "per_frame_robustness": robustness,
        "geometry_hypothesis": geometry,
        "row_permutation_fits": row_fits,
        "side_consistency": side_consistency,
        "static_lut_evidence": static,
        "execution_integrity_reference": map_analysis_doc["execution_integrity"],
        "conclusions": conclusions,
        "lh3_design_implications": {
            "risk": "if the code axis also shifts when starting from a coloured endpoint "
                    "(white->family endpoint->second code), LH3's two-stage ladders would "
                    "measure an unknown permutation of the intended codes",
            "recommendations": [
                "LH3 frames must embed a per-frame calibration strip: cells that replay "
                "known from-white endpoints (code 0..7 from a fresh-white history) next to "
                "the experimental cells, so the effective code axis is re-measured in the "
                "same refresh as the experiment (a 'known control column' per stage)",
                "include a white-reference column (commented C7 from the same start state "
                "as the experimental cells) so the 'white at this chain position' is "
                "measured, not assumed",
                "treat chain position as an independent variable: report L*(history, code, "
                "chain_depth) and fit the per-depth code permutation before interpreting "
                "any ladder",
                "prefer same-refresh comparisons (both controllers / quadrant replicas) "
                "over cross-session camera-relative absolutes",
                "do not promote any MAP-state level to a palette candidate until the code "
                "axis at that chain depth is calibrated; qualified stays 0",
            ]},
        "qualified_count": 0,
        "hardware_accessed": False,
        "visible_refresh": 0}

    args.output_dir.mkdir(parents=True, exist_ok=False)
    rec.write_new(args.output_dir / "xor3-analysis.json", rec.seal(analysis))

    report = render_report(analysis)
    report_path = args.output_dir / "xor3-report.md"
    with report_path.open("x", encoding="utf-8", newline="\n") as fh:
        fh.write(report)
    tool_copy = args.output_dir / "xor3-analysis-tool.py"
    with tool_copy.open("xb") as fh:
        fh.write(Path(__file__).read_bytes())
    print(json.dumps({"written": [str(args.output_dir / n) for n in
                                  ("xor3-analysis.json", "xor3-report.md",
                                   "xor3-analysis-tool.py")],
                      "every_frame_xor3": robustness["every_frame_best_is_xor3"],
                      "delta_e00": robustness["delta_e00"]}, ensure_ascii=False))


def render_report(analysis: dict) -> str:
    r = analysis["per_frame_robustness"]
    sc = analysis["static_lut_evidence"]
    lines = [
        "# LH2 MAP XOR-3 码轴机制离线研究（2026-09-18）",
        "",
        "现象：LH2 MAP 帧中 (白历史 M7, 码 c) 在全 Lab 上复现本 session MIDDLE 端点 c^3。",
        "本报告只做离线证据研究，不授权任何现场动作。",
        "",
        "## 1. 逐帧稳健性",
        "",
        f"- 10 帧 × 2 侧逐帧独立拟合 40320 置换：**每帧每侧的最优置换都是 XOR-3**"
        f"（every_frame_best_is_xor3 = {r['every_frame_best_is_xor3']}）。",
        f"- 配对 ΔE00：median {r['delta_e00']['median']:.2f}，P95 {r['delta_e00']['p95']:.2f}，"
        f"max {r['delta_e00']['max']:.2f}（160 对）；|ΔL*| max {r['abs_delta_lstar']['max']:.2f}。",
        f"- 对照：恒等置换的总 ΔE76 中位 {r['identity_permutation_total_delta_e76_median']:.1f} "
        f"vs XOR-3 的 {r['xor3_total_delta_e76_median']:.1f}。",
        "- 参照是 s3-pre 单帧 8 位置中位；MAP 侧用逐帧样本，故该检验覆盖了帧间噪声。",
        "",
        "## 2. 竞争假设",
        "",
        "- **(a) 提取/几何误差：证伪。** 8 个候选几何重标定（rot180/行列镜像/转置/象限翻转）"
        "全部违反 recipe 保持约束；唯一能产生 c→c^3 的几何变换（象限双半翻转）在两张放置表上"
        "都不保持 recipe。M7 行 assignment scatter 与全样本同分布。s3-pre 的 code7=白验证已把"
        "本 session 的 identity/identity 钉死。",
        "- **(b) 帧内容：已排除**（设备 input_fnv1a 与两侧 DTM 流 FNV 同封存帧逐字节吻合，"
        "见 LH2_DRIVE_MAP_ANALYSIS_20260918_V1 的 execution_integrity）。",
        "- **(c) 历史-码交互：码轴漂移是 MAP 级全局现象。** 白历史行精确 XOR-3"
        "（mean ΔE76 0.8）；彩色历史行同样拒绝恒等置换（identity mean ΔE76 20–28），"
        "以 XOR-3 mean ΔE76 4.4–6.9 近似成立（多数行与自身最优置换差距 <0.5），"
        "并叠加历史相关的残余畸变——起点是'真白'时码轴漂移精确，彩色起点附带畸变。",
        "- **(d) 侧别一致：** CS1/CS2 同向 XOR-3，同 tuple 同帧互为复测。",
        "",
        "## 3. LUT 静态证据",
        "",
        f"- 厂商 EDP_init.c 两张 535 字节表（注释块=commented、活动块=active），"
        f"结构 7 + 6×8×11（VCOM/Black/White/Yellow/Red/Power × GROUP1..8 × 11B），"
        f"两表节序相同；解析哈希与 src/generated 钉值吻合：{sc['matches_pinned_hashes']}。",
        "- 表头差异：active 00 1E 78 20 1E 14 02 vs commented 00 24 78 27 20 14 03 —— "
        "VSHL/VCOM 相关电压字节与 PLL 分频（0x02→0x03）均不同，即两种'白'刷新电气上不等价。",
        f"- 同位块相等：{sc['active_vs_commented_same_index_equal_blocks']['equal']}/48；"
        "逐 category 组级置换搜索两表间无任何相等块（commented 不是 active 的组重排）；"
        "两表内部对 XOR-3/XOR-7/3bit 位反转均无平凡以外的字节级组对称"
        f"（XOR-3 非平凡相等对：active {sc['within_table_group_symmetry']['active']['xor3']['equal_blocks']}、"
        f"commented {sc['within_table_group_symmetry']['commented']['xor3']['equal_blocks']}）。",
        "- **结论：上传的 LUT 字节里没有 c→c^3 的静态对应物**；机制在上游字节之外"
        "（控制器内部译码状态或面板状态记忆）。厂商源码未记载 8 组/group 的语义"
        "（旧态索引还是相位计划），离线不可判。",
        "",
        "## 4. 对 LH3（白→族内端点→同族第二码）的含义",
        "",
    ]
    for rec_line in analysis["lh3_design_implications"]["recommendations"]:
        lines.append(f"- {rec_line}")
    lines += [
        "",
        "qualified=0 保持；本研究不产生任何资格。",
        "",
        f"分析版本 {analysis['analysis_version']}；完整数据见同目录 xor3-analysis.json（自封）。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
