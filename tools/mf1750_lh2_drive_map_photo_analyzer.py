#!/usr/bin/env python3
"""Offline 10-frame 128-ROI extractor for the LH2 drive-map MAP frame.

Read-only image analysis: no device, network, relay or camera access. The
side/orientation mapping is NOT re-solved here: it is inherited from the sealed
LH1 rebound MIDDLE extraction (same physical bench arrangement, same camera
mount, same placement tables; CS1=left/CS2=right, identity/identity). The MAP
frame writes code 4*h + quadrant per cell, so a colour-cluster mapping solver
is not applicable; every (history, code) pair appears exactly once per side.

The 10 map-frames give per-ROI medians and N=10 noise statistics; the optional
anchor frame (post-map.jpg, same screen state, separate capture) is sampled
through the same homography pipeline and reported per ROI as an independent
re-measurement against the 10-frame median.
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

ANALYZER_VERSION = "mf1750-lh2-drive-map-photo-analyzer-v1"
# Same user-waived geometric gate as the MIDDLE/TARGET V2 analyses; optical
# thresholds stay frozen at MF1750_LIGHTNESS_TEST_V1_20260911.
ASSIGNMENT_SCATTER_LIMIT_PX = base.ASSIGNMENT_SCATTER_LIMIT_PX
RECIPE = re.compile(r"LH2-S7-M([0-7])-H([01])")

# Session-adaptive cell detection. The 2026-09-18 evening MAP batch was captured
# under much lower ambient light than the 2026-09-17 MIDDLE batch (scene median
# channel-sum 95 vs 377 with byte-identical camera settings), so the base
# analyzer's fixed `sums < 430` dark mask selects essentially the whole scene.
# Cells are still darker than the local screen white, so a morphological
# blackhat (161 px closing minus image) at a fixed 60-sum threshold finds them.
# Everything downstream (clustering, lattice assignment, homography, ROI
# sampling) is the base pipeline unchanged.
BLACKHAT_KERNEL_PX = 161
BLACKHAT_THRESHOLD = 60.0


def detect_centers(bgr: np.ndarray) -> np.ndarray:
    sums = bgr.astype(np.int32).sum(axis=2).astype(np.float32)
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (BLACKHAT_KERNEL_PX, BLACKHAT_KERNEL_PX))
    blackhat = cv2.morphologyEx(sums, cv2.MORPH_CLOSE, kernel) - sums
    mask = (blackhat > BLACKHAT_THRESHOLD).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    centers = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[i])
        if area < base.MIN_AREA or area > 2 * base.MAX_AREA:
            continue
        if w > h * 1.4 and area > 8000:  # two horizontally merged cells
            centers.append((x + w / 4.0, y + h / 2.0))
            centers.append((x + 3 * w / 4.0, y + h / 2.0))
            continue
        if h > w * 1.4 and area > 8000:  # two vertically merged cells
            centers.append((x + w / 2.0, y + h / 4.0))
            centers.append((x + w / 2.0, y + 3 * h / 4.0))
            continue
        if area > base.MAX_AREA or not 0.45 <= w / h <= 1.30:
            continue
        centers.append((x + w / 2.0, y + h / 2.0))
    return np.array(centers, dtype=np.float64)


def load_middle_mapping(path: Path) -> dict:
    """Bind the sealed MIDDLE mapping; refuse any other side/orientation."""
    data = json.loads(path.read_text(encoding="utf-8"))
    mapping = data.get("mapping_evidence", {}).get("mapping")
    want = {"side_to_ctrl": {"CS1": "left", "CS2": "right"},
            "transform_per_side": {"left": "identity", "right": "identity"}}
    if not isinstance(mapping, dict) or {k: mapping.get(k) for k in want} != want:
        raise SystemExit("sealed MIDDLE mapping is not the inherited CS1=left identity/identity")
    return mapping


def recipe_index(recipe_id: str) -> int:
    m = RECIPE.fullmatch(recipe_id)
    if not m:
        raise SystemExit(f"recipe id malformed: {recipe_id}")
    return int(m.group(1)) + 8 * int(m.group(2))


def recipe_codes(recipe_id: str) -> tuple[int, int]:
    m = RECIPE.fullmatch(recipe_id)
    if not m:
        raise SystemExit(f"recipe id malformed: {recipe_id}")
    return int(m.group(1)), int(m.group(2))


def map_code(code_half: int, row: int, col: int) -> int:
    quadrant = (2 if row >= 4 else 0) + (1 if col >= 4 else 0)
    return 4 * code_half + quadrant


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frames-dir", type=Path, required=True,
                   help="directory with exactly 10 same-state MAP frames + sidecars")
    p.add_argument("--package", type=Path, required=True,
                   help="sealed LH2 drive-map package (observations.blank.json, contract.json, generated/)")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--identity", type=Path, required=True,
                   help="JSON with the sealed MAP identity fields")
    p.add_argument("--middle-extraction", type=Path, required=True,
                   help="sealed MIDDLE extraction.json carrying the solved mapping")
    p.add_argument("--anchor-frame", type=Path, default=None,
                   help="optional 11th same-state capture (post-map.jpg) sampled as re-test")
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
    for key, want in blank["identity"].items():
        if key in identity and identity[key] != want:
            raise SystemExit(f"identity mismatch vs blank package: {key}")
    contract = json.loads((args.package / "contract.json").read_text(encoding="utf-8"))
    map_action = contract["actions"][2]
    if map_action["frame"]["sha256"] != blank["identity"]["frame_sha256"]:
        raise SystemExit("contract MAP frame sha does not match blank identity")
    inc = args.package / "generated" / "ec5_lightness_lh2_drive_map_v1_identity.inc"
    placement_all = base.load_placement(inc)
    placement = {"CS1": placement_all["kRecipeAtCellCs1"], "CS2": placement_all["kRecipeAtCellCs2"]}
    for e in entries:
        roi = e["roi"]
        col = (roi["x"] - base.GRID_X0) // (base.CELL_W + base.GAP)
        row = (roi["y"] - base.GRID_Y0) // (base.CELL_H + base.GAP)
        if (roi["x"] - base.GRID_X0) % (base.CELL_W + base.GAP) or \
                (roi["y"] - base.GRID_Y0) % (base.CELL_H + base.GAP):
            raise SystemExit("blank ROI off grid")
        want = recipe_index(e["recipe_id"])
        got = placement[e["controller"]][row * base.COLS + col]
        if want != got:
            raise SystemExit(f"blank/placement mismatch at {e['controller']} r{row} c{col}")
        _, half = recipe_codes(e["recipe_id"])
        code = map_code(half, row, col)
        if e["comparison_id"] != f"MAP_C{code}":
            raise SystemExit(f"comparison_id/map_code mismatch at {e['controller']} r{row} c{col}")

    lab_crosscheck_max_abs = base.crosscheck_lab()
    frames = sorted(args.frames_dir.glob("*.jpg"))
    if len(frames) != 10:
        raise SystemExit("exactly 10 frames required")
    if not all(f.with_suffix(".capture.json").exists() for f in frames):
        raise SystemExit("every frame needs its capture sidecar")
    if args.anchor_frame is not None and \
            not args.anchor_frame.with_suffix(".capture.json").exists():
        raise SystemExit("anchor frame needs its capture sidecar")

    side_to_ctrl = mapping["side_to_ctrl"]
    ctrl_of_side = {side: ctrl for ctrl, side in side_to_ctrl.items()}
    transform_of = {side: base.TRANSFORMS[name]
                    for side, name in mapping["transform_per_side"].items()}

    # Pass 1: geometry from the first frame; reference centres for all 64 cells
    # per side (detected centres plus homography-predicted misses).
    bgr0 = cv2.imread(str(frames[0]))
    if bgr0 is None or bgr0.shape[:2] != (3000, 4000):
        raise SystemExit("first frame unreadable or wrong size")
    comps = base.grid_components(detect_centers(bgr0))
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

    def frame_homographies(bgr: np.ndarray, frame_name: str) -> tuple[dict, dict]:
        comps_f = base.grid_components(detect_centers(bgr))
        sides = {"left": comps_f[0] if comps_f[0][:, 0].mean() < comps_f[1][:, 0].mean() else comps_f[1],
                 "right": comps_f[1] if comps_f[0][:, 0].mean() < comps_f[1][:, 0].mean() else comps_f[0]}
        rep = {"frame": frame_name}
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
                    raise SystemExit(f"{frame_name} {side}: unmatched cell at {(x, y)}")
                key = ref_keys[j]
                if key in used:
                    raise SystemExit(f"{frame_name} {side}: duplicate assignment at {key}")
                used.add(key)
                lattice[key] = (float(x), float(y))
            if len(lattice) < 50:
                raise SystemExit(f"{frame_name} {side}: only {len(lattice)} cells")
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
                raise SystemExit(f"camera drift over limit in {frame_name}: median {median_drift}")
            homographies[ctrl_of_side[side]] = h
            rep[ctrl_of_side[side]] = {"detected_cells": len(lattice),
                                       "reprojection_rmse_px": rmse,
                                       "median_assignment_drift_px": median_drift,
                                       "max_assignment_drift_px": max_drift}
            rep[ctrl_of_side[side]]["lattice"] = lattice
        return homographies, rep

    # Pass 2: full ROI sampling on all 10 frames with per-frame homography.
    per_roi_samples: dict[int, list[np.ndarray]] = {i: [] for i in range(128)}
    per_roi_quality: dict[int, list[dict]] = {i: [] for i in range(128)}
    cell_tracks: dict[tuple[str, tuple], list[tuple[float, float]]] = {}
    frame_reports = []
    for frame_path in frames:
        bgr = cv2.imread(str(frame_path))
        if bgr is None or bgr.shape[:2] != (3000, 4000):
            raise SystemExit(f"frame unreadable or wrong size: {frame_path}")
        homographies, frame_rep = frame_homographies(bgr, frame_path.name)
        for ctrl in ("CS1", "CS2"):
            for key, xy in frame_rep[ctrl].pop("lattice").items():
                side = side_to_ctrl[ctrl]
                cell_tracks.setdefault((side, key), []).append(xy)
        for i, e in enumerate(entries):
            med, quality = base.sample_roi_lab(bgr, homographies[e["controller"]], e["roi"])
            if med is None:
                raise SystemExit(f"ROI outside image or empty: {json.dumps(e)}")
            per_roi_samples[i].append(med)
            per_roi_quality[i].append(quality)
        frame_reports.append(frame_rep)

    # Pass 3 (optional): anchor frame sampled through its own homography as an
    # independent re-measurement of the same screen state.
    anchor_samples: dict[int, np.ndarray] | None = None
    anchor_report = None
    if args.anchor_frame is not None:
        bgr_a = cv2.imread(str(args.anchor_frame))
        if bgr_a is None or bgr_a.shape[:2] != (3000, 4000):
            raise SystemExit("anchor frame unreadable or wrong size")
        homographies_a, anchor_report = frame_homographies(bgr_a, args.anchor_frame.name)
        anchor_report.pop("frame")
        for ctrl in ("CS1", "CS2"):
            anchor_report[ctrl].pop("lattice")
        anchor_samples = {}
        for i, e in enumerate(entries):
            med, _ = base.sample_roi_lab(bgr_a, homographies_a[e["controller"]], e["roi"])
            if med is None:
                raise SystemExit(f"anchor ROI outside image or empty: {json.dumps(e)}")
            anchor_samples[i] = med

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
        middle_code, code_half = recipe_codes(e["recipe_id"])
        code = map_code(code_half, row_l, col_l)
        row = {"entry": i, "recipe_id": e["recipe_id"], "controller": e["controller"],
               "position": e["position"], "comparison_id": e["comparison_id"],
               "middle_code": middle_code, "code_half": code_half, "map_code": code,
               "grid_row": row_l, "grid_col": col_l,
               "lab_median": [float(v) for v in med],
               "lab_samples": [[float(v) for v in s] for s in samples],
               "lstar_mad": mad_l, "lstar_ci95_half_width": ci_l,
               "assignment_scatter_px": scatter,
               "quality_pass": bool(max_clip <= base.CLIP_LIMIT
                                    and (scatter is None or scatter <= ASSIGNMENT_SCATTER_LIMIT_PX)),
               "single_pixel_uniform": bool(max_uniform_p95 <= base.UNIFORM_P95_DE76_LIMIT),
               "max_clip_fraction": max_clip,
               "max_uniform_p95_delta_e76": max_uniform_p95}
        if anchor_samples is not None:
            a = anchor_samples[i]
            row["anchor_lab"] = [float(v) for v in a]
            row["anchor_delta_lstar"] = float(a[0] - med[0])
            row["anchor_delta_e76"] = float(np.linalg.norm(a - med))
        rows.append(row)
    report = {"identity": identity, "analyzer_version": ANALYZER_VERSION,
              "assignment_scatter_limit_px": ASSIGNMENT_SCATTER_LIMIT_PX,
              "placement_crosscheck": "PASS",
              "lab_crosscheck_max_abs": lab_crosscheck_max_abs,
              "mapping_source": {"inherited_from_sealed_middle_extraction": True,
                                 "middle_extraction_path": str(args.middle_extraction),
                                 "middle_extraction_sha256": middle_sha,
                                 "mapping": mapping},
              "map_frame_contract": {"contract_id": contract["contract_id"],
                                     "action_sha256": map_action["action_id"],
                                     "frame_sha256": map_action["frame"]["sha256"],
                                     "frame_histogram": map_action["frame"]["histogram"]},
              "cell_detection": {"method": "morphological-blackhat",
                                 "reason": "2026-09-18 evening session is much darker than the 2026-09-17 MIDDLE session at identical camera settings; fixed sums<430 mask selects the whole scene",
                                 "kernel_px": BLACKHAT_KERNEL_PX,
                                 "threshold_sum": BLACKHAT_THRESHOLD},
              "anchor_frame": {"path": str(args.anchor_frame),
                               "sha256": base.sha256(args.anchor_frame.read_bytes()),
                               "report": anchor_report} if args.anchor_frame else None,
              "frames": frame_reports, "rows": rows}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    out = args.output_dir / "extraction.json"
    out.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(out), "lab_crosscheck_max_abs": lab_crosscheck_max_abs,
                      "mapping": mapping, "frames": len(frames),
                      "anchor": args.anchor_frame.name if args.anchor_frame else None},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
