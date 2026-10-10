#!/usr/bin/env python3
"""Offline 10-frame 128-ROI extractor for the LH1 rebound V2 TARGET frame.

Read-only image analysis: no device, network, relay or camera access. The
side/orientation mapping is NOT re-solved here: it is inherited from the sealed
MIDDLE extraction (same physical bench arrangement, same camera mount; the
180-degree CS2 placement was user-confirmed). TARGET content differs by design:
T3-group cells share target code 3 and T7-group cells share target code 7
(white, mostly undetectable), so the MIDDLE colour-cluster mapping solver is
not applicable to this frame.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import mf1750_lh1_rebound_v2_middle_photo_analyzer as base  # noqa: E402

ANALYZER_VERSION = "mf1750-lh1-rebound-v2-target-photo-analyzer-v1"
# Same user-waived geometric gate as the MIDDLE analysis V2; optical thresholds
# stay frozen at MF1750_LIGHTNESS_TEST_V1_20260911.
ASSIGNMENT_SCATTER_LIMIT_PX = base.ASSIGNMENT_SCATTER_LIMIT_PX
RECIPE = re.compile(r"LH1-S7-M([0-7])-T([37])")


def load_middle_mapping(path: Path) -> dict:
    """Bind the sealed MIDDLE mapping; refuse any other side/orientation."""
    data = json.loads(path.read_text(encoding="utf-8"))
    mapping = data.get("mapping_evidence", {}).get("mapping")
    want = {"side_to_ctrl": {"CS1": "left", "CS2": "right"},
            "transform_per_side": {"left": "identity", "right": "identity"}}
    if not isinstance(mapping, dict) or {k: mapping.get(k) for k in want} != want:
        raise SystemExit("sealed MIDDLE mapping is not the inherited CS1=left identity/identity")
    return mapping


def recipe_codes(recipe_id: str) -> tuple[int, int]:
    m = RECIPE.fullmatch(recipe_id)
    if not m:
        raise SystemExit(f"recipe id malformed: {recipe_id}")
    return int(m.group(1)), int(m.group(2))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frames-dir", type=Path, required=True)
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--identity", type=Path, required=True,
                   help="JSON with the sealed TARGET identity fields")
    p.add_argument("--middle-extraction", type=Path, required=True,
                   help="sealed MIDDLE extraction.json carrying the solved mapping")
    args = p.parse_args()
    if args.output_dir.exists():
        raise SystemExit("output dir must not exist (O_EXCL batch)")

    identity = json.loads(args.identity.read_text(encoding="utf-8"))
    middle_sha = base.sha256(args.middle_extraction.read_bytes())
    mapping = load_middle_mapping(args.middle_extraction)
    blank = json.loads((args.package / "observations.blank.json").read_text(encoding="utf-8"))
    entries = blank["observations"]
    if len(entries) != 128:
        raise SystemExit("128 blank observations required")
    inc = args.package / "generated" / "ec5_lightness_lh1_rebound_v2_identity.inc"
    placement_all = base.load_placement(inc)
    placement = {"CS1": placement_all["kRecipeAtCellCs1"], "CS2": placement_all["kRecipeAtCellCs2"]}
    for e in entries:
        roi = e["roi"]
        col = (roi["x"] - base.GRID_X0) // (base.CELL_W + base.GAP)
        row = (roi["y"] - base.GRID_Y0) // (base.CELL_H + base.GAP)
        if (roi["x"] - base.GRID_X0) % (base.CELL_W + base.GAP) or \
                (roi["y"] - base.GRID_Y0) % (base.CELL_H + base.GAP):
            raise SystemExit("blank ROI off grid")
        want = base.recipe_index(e["recipe_id"])
        got = placement[e["controller"]][row * base.COLS + col]
        if want != got:
            raise SystemExit(f"blank/placement mismatch at {e['controller']} r{row} c{col}")

    lab_crosscheck_max_abs = base.crosscheck_lab()
    frames = sorted(args.frames_dir.glob("*.jpg"))
    if len(frames) != 10:
        raise SystemExit("exactly 10 frames required")
    if not all(f.with_suffix(".capture.json").exists() for f in frames):
        raise SystemExit("every frame needs its capture sidecar")

    side_to_ctrl = mapping["side_to_ctrl"]
    ctrl_of_side = {side: ctrl for ctrl, side in side_to_ctrl.items()}
    transform_of = {side: base.TRANSFORMS[name]
                    for side, name in mapping["transform_per_side"].items()}

    # Pass 1: geometry from the first frame; reference centres for all 64 cells
    # per side (detected centres plus homography-predicted misses).
    bgr0 = cv2.imread(str(frames[0]))
    if bgr0 is None or bgr0.shape[:2] != (3000, 4000):
        raise SystemExit("first frame unreadable or wrong size")
    comps = base.grid_components(base.detect_centers(bgr0))
    side_of = {"left": comps[0] if comps[0][:, 0].mean() < comps[1][:, 0].mean() else comps[1],
               "right": comps[1] if comps[0][:, 0].mean() < comps[1][:, 0].mean() else comps[0]}
    lattices = {}
    for side, pts in side_of.items():
        lattices[side], _ = base.assign_lattice(pts)
    reference_centers: dict[str, dict] = {}
    for side, lattice in lattices.items():
        transform = transform_of[side]
        src, dst = [], []
        for (ir, ic), (x, y) in lattice.items():
            matched = [(r, c) for r in range(base.ROWS) for c in range(base.COLS)
                       if transform(r, c) == (ir, ic)]
            (r, c), = matched
            src.append(base.local_center(r, c))
            dst.append((x, y))
        h, _ = cv2.findHomography(np.array(src), np.array(dst), 0)
        ref = {}
        for ir in range(base.ROWS):
            for ic in range(base.COLS):
                if (ir, ic) in lattice:
                    ref[(ir, ic)] = lattice[(ir, ic)]
                else:
                    matched = [(r, c) for r in range(base.ROWS) for c in range(base.COLS)
                               if transform(r, c) == (ir, ic)]
                    (r, c), = matched
                    ref[(ir, ic)] = tuple(cv2.perspectiveTransform(
                        np.array([[base.local_center(r, c)]], dtype=np.float64), h)[0, 0])
        reference_centers[side] = ref

    # Pass 2: full ROI sampling on all 10 frames with per-frame homography.
    per_roi_samples: dict[int, list[np.ndarray]] = {i: [] for i in range(128)}
    per_roi_quality: dict[int, list[dict]] = {i: [] for i in range(128)}
    cell_tracks: dict[tuple[str, tuple], list[tuple[float, float]]] = {}
    frame_reports = []
    for frame_path in frames:
        bgr = cv2.imread(str(frame_path))
        if bgr is None or bgr.shape[:2] != (3000, 4000):
            raise SystemExit(f"frame unreadable or wrong size: {frame_path}")
        comps = base.grid_components(base.detect_centers(bgr))
        sides = {"left": comps[0] if comps[0][:, 0].mean() < comps[1][:, 0].mean() else comps[1],
                 "right": comps[1] if comps[0][:, 0].mean() < comps[1][:, 0].mean() else comps[0]}
        frame_rep = {"frame": frame_path.name}
        homographies = {}
        for side, pts in sides.items():
            lattice: dict = {}
            ref = reference_centers[side]
            ref_keys = sorted(ref)
            ref_pts = np.array([ref[k] for k in ref_keys])
            used = set()
            for x, y in pts:
                d = np.sqrt(((ref_pts - (x, y)) ** 2).sum(axis=1))
                j = int(np.argmin(d))
                if d[j] > 40:
                    raise SystemExit(f"{frame_path.name} {side}: unmatched cell at {(x, y)}")
                key = ref_keys[j]
                if key in used:
                    raise SystemExit(f"{frame_path.name} {side}: duplicate assignment at {key}")
                used.add(key)
                lattice[key] = (float(x), float(y))
            if len(lattice) < 50:
                raise SystemExit(f"{frame_path.name} {side}: only {len(lattice)} cells")
            for key, xy in lattice.items():
                cell_tracks.setdefault((side, key), []).append(xy)
            transform = transform_of[side]
            src, dst = [], []
            for (ir, ic), (x, y) in lattice.items():
                matched = [(r, c) for r in range(base.ROWS) for c in range(base.COLS)
                           if transform(r, c) == (ir, ic)]
                (r, c), = matched
                src.append(base.local_center(r, c))
                dst.append((x, y))
            h, _ = cv2.findHomography(np.array(src), np.array(dst), cv2.LMEDS)
            proj = cv2.perspectiveTransform(np.array(src).reshape(-1, 1, 2), h).reshape(-1, 2)
            rmse = float(np.sqrt(np.mean(np.sum((proj - np.array(dst)) ** 2, axis=1))))
            detected_ref = [k for k in lattice if lattices[side].get(k) is not None]
            displacements = [math.dist(lattices[side][k], lattice[k]) for k in detected_ref]
            median_drift = float(np.median(displacements)) if displacements else 0.0
            max_drift = float(max(displacements)) if displacements else 0.0
            if median_drift > 2.0:
                raise SystemExit(f"camera drift over limit in {frame_path.name}: median {median_drift}")
            homographies[ctrl_of_side[side]] = h
            frame_rep[ctrl_of_side[side]] = {"detected_cells": len(lattice),
                                             "reprojection_rmse_px": rmse,
                                             "median_assignment_drift_px": median_drift,
                                             "max_assignment_drift_px": max_drift}
        for i, e in enumerate(entries):
            med, quality = base.sample_roi_lab(bgr, homographies[e["controller"]], e["roi"])
            if med is None:
                raise SystemExit(f"ROI outside image or empty: {json.dumps(e)}")
            per_roi_samples[i].append(med)
            per_roi_quality[i].append(quality)
        frame_reports.append(frame_rep)

    rows = []
    transform_of_ctrl = {ctrl_of_side[side]: base.TRANSFORMS[mapping["transform_per_side"][side]]
                         for side in side_of}
    for i, e in enumerate(entries):
        samples = np.stack(per_roi_samples[i])
        med = np.median(samples, axis=0)
        lstar = samples[:, 0]
        mad_l = float(np.median(np.abs(lstar - med[0])))
        ci_l = float(2.262 * np.std(lstar, ddof=1) / math.sqrt(len(lstar)))
        qualities = per_roi_quality[i]
        max_clip = max(max(q["clip_high_fraction"], q["clip_low_fraction"]) for q in qualities)
        max_uniform_p95 = max(q["uniform_p95_delta_e76"] for q in qualities)
        row_l = (e["roi"]["y"] - base.GRID_Y0) // (base.CELL_H + base.GAP)
        col_l = (e["roi"]["x"] - base.GRID_X0) // (base.CELL_W + base.GAP)
        ikey = transform_of_ctrl[e["controller"]](row_l, col_l)
        track = cell_tracks.get((side_to_ctrl[e["controller"]], ikey), [])
        if len(track) >= 2:
            tmed = np.median(np.array(track), axis=0)
            scatter = float(max(math.dist(p, tuple(tmed)) for p in track))
        else:
            scatter = None  # undetected (near-white) cells: position comes from homography
        middle_code, target_code = recipe_codes(e["recipe_id"])
        rows.append({"entry": i, "recipe_id": e["recipe_id"], "controller": e["controller"],
                     "position": e["position"],
                     "middle_code": middle_code, "target_code": target_code,
                     "lab_median": [float(v) for v in med],
                     "lab_samples": [[float(v) for v in s] for s in samples],
                     "lstar_mad": mad_l, "lstar_ci95_half_width": ci_l,
                     "assignment_scatter_px": scatter,
                     "quality_pass": bool(max_clip <= base.CLIP_LIMIT
                                          and (scatter is None or scatter <= ASSIGNMENT_SCATTER_LIMIT_PX)),
                     "single_pixel_uniform": bool(max_uniform_p95 <= base.UNIFORM_P95_DE76_LIMIT),
                     "max_clip_fraction": max_clip,
                     "max_uniform_p95_delta_e76": max_uniform_p95})
    report = {"identity": identity, "analyzer_version": ANALYZER_VERSION,
              "assignment_scatter_limit_px": ASSIGNMENT_SCATTER_LIMIT_PX,
              "placement_crosscheck": "PASS",
              "lab_crosscheck_max_abs": lab_crosscheck_max_abs,
              "mapping_source": {"inherited_from_sealed_middle_extraction": True,
                                 "middle_extraction_path": str(args.middle_extraction),
                                 "middle_extraction_sha256": middle_sha,
                                 "mapping": mapping},
              "frames": frame_reports, "rows": rows}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    out = args.output_dir / "extraction.json"
    out.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(out), "lab_crosscheck_max_abs": lab_crosscheck_max_abs,
                      "mapping": mapping, "frames": len(frames)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
