#!/usr/bin/env python3
"""Offline 10-frame 128-ROI extractor for the LH3 dose DOSE1/DOSE2 frames.

Read-only image analysis: no device, network, relay or camera access. Variant
of the LH2 drive-map analyzer for the dose layout: column c of each side's 8x8
grid carries code c in all 8 rows (recipe_id LH3D-S7-D{code}-R{row}), so there
is no 4*h+quadrant decode and no placement-table lookup — the recipe id pins
(code, row) directly and must agree with the blank ROI grid position.

The side/orientation mapping is NOT re-solved here: it is inherited from the
sealed LH1 rebound MIDDLE extraction (same physical bench arrangement, same
camera mount; CS1=left/CS2=right, identity/identity). The 2026-09-24 session
moved the camera slightly (keyboard in frame, panel shifted) and is dim, but
per-frame homographies and the dark-session blackhat detector handle both; the
session is internally consistent, which is what the dose1-vs-dose2 relative
comparison needs.

The two dose frames are byte-identical, so the stage is selected explicitly
(--stage DOSE1/DOSE2) and bound through the contract action id, not the frame
sha. --live-result binds the extraction to the sealed device terminal record
of that stage. The 10 frames give per-ROI medians and N=10 noise statistics;
the optional anchor frame is sampled as an independent re-measurement.
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

from host.static_photo.common import attach_integrity  # noqa: E402
from tools import mf1750_lh1_rebound_v2_middle_photo_analyzer as base  # noqa: E402
from tools import mf1750_lh2_drive_map_photo_analyzer as map_analyzer  # noqa: E402

ANALYZER_VERSION = "mf1750-lh3-dose-photo-analyzer-v1"
ASSIGNMENT_SCATTER_LIMIT_PX = base.ASSIGNMENT_SCATTER_LIMIT_PX
RECIPE = re.compile(r"LH3D-S7-D([0-7])-R([0-7])")
STAGE_ORDINAL = {"DOSE1": 2, "DOSE2": 3}
# Variant knobs: the PAL1 measured-palette analyzer
# (tools/mf1750_pal1_photo_analyzer.py) reuses this whole pipeline with a PAL1
# recipe pattern, stage map and record kinds.
RESULT_KIND = "mf1750-lh3-dose-result-v1"
EXTRACTION_KIND = "mf1750-lh3-dose-extraction-v1"
STAGE_CONTRACT_KEY = "dose_stage_contract"
COMPARISON_PREFIX = "DOSE_C"

detect_centers = map_analyzer.detect_centers
load_middle_mapping = map_analyzer.load_middle_mapping
# Component/row thresholds; the PAL2 OTP stock frame has three white-ish
# columns (2/5/7) that produce no detectable blob, so its variant relaxes them.
MIN_COMPONENT_CELLS = 50
MIN_ROW_CELLS = 6


def grid_components(centers):
    """Two dense cell matrices; spurious tiny clusters are dropped, not fatal."""
    comps = _grid_components_impl(centers)
    big = [c for c in comps if len(c) >= MIN_COMPONENT_CELLS]
    if len(big) < 2:
        raise SystemExit(f"two dense matrices required; component sizes: {[len(c) for c in comps]}")
    return big[:2]


def _grid_components_impl(centers):
    import numpy as np
    d = np.sqrt(((centers[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2))
    adj = (d > 70) & (d < 175)
    np.fill_diagonal(adj, False)
    seen = np.zeros(len(centers), bool)
    comps = []
    for start in range(len(centers)):
        if seen[start]:
            continue
        stack, comp = [start], []
        seen[start] = True
        while stack:
            node = stack.pop()
            comp.append(node)
            for nxt in np.flatnonzero(adj[node]):
                if not seen[nxt]:
                    seen[nxt] = True
                    stack.append(int(nxt))
        comps.append(centers[sorted(comp)])
    comps.sort(key=len, reverse=True)
    return comps


def assign_dose_lattice(centers: np.ndarray) -> tuple[dict, float]:
    """assign_lattice variant tolerating the invisible code-7 column.

    The dose layout paints column 7 white on a white background, so its 8
    cells produce no detectable component and no row is ever complete; the
    base analyzer's complete-row column seeding cannot run. Rows cluster by
    derotated y exactly as in the base pipeline; columns are then anchored
    from the left (the dark codes 0.. always detect, even in a dim session)
    using the within-row pitch, with internal gaps splitting column indices.
    Missing trailing columns stay absent — the homography predicts them.
    """
    centers = np.asarray(centers, dtype=np.float64)
    best = None
    for theta in np.arange(-8.0, 8.0, 0.1):
        rad = math.radians(theta)
        rot = np.array([[math.cos(rad), -math.sin(rad)], [math.sin(rad), math.cos(rad)]])
        rc = centers @ rot.T
        labels = base._cluster1d(rc[:, 1], base.ROWS)
        var = float(np.sum([np.var(rc[labels == k, 1]) for k in range(base.ROWS)]))
        if best is None or var < best[0]:
            best = (var, theta, rc)
    _, theta, rc = best
    row_labels = base._cluster1d(rc[:, 1], base.ROWS)
    rows: dict[int, list[tuple[float, float]]] = {}
    for i, (x, y) in enumerate(rc):
        rows.setdefault(int(row_labels[i]), []).append((float(x), float(y)))
    diffs = [b[0] - a[0]
             for cells in rows.values()
             for a, b in zip(sorted(cells), sorted(cells)[1:])]
    if not diffs:
        raise SystemExit("no within-row pairs; lattice seeding unreliable")
    cells_per_row = min(len(cells) for cells in rows.values())
    if cells_per_row < MIN_ROW_CELLS:
        raise SystemExit(
            f"row has only {cells_per_row} cells; column seeding requires "
            f"at least {MIN_ROW_CELLS} detected")
    # Candidate column sets (must include the dark code-0 anchor column) are
    # scored by the x-model residual; the pitch/gap walk alone mis-assigns
    # when an invisible column leaves irregular gaps (PAL2 OTP stock).
    from itertools import combinations
    assigned = None
    best_residual = None
    for cols in combinations(range(1, base.COLS), cells_per_row - 1):
        cols = (0,) + cols
        trial: dict[int, list[tuple[int, float, float]]] = {}
        for r, cells in rows.items():
            ordered = sorted(cells)
            if len(ordered) != cells_per_row:
                break
            trial[r] = [(c, x, y) for c, (x, y) in zip(cols, ordered)]
        else:
            src, dstx = [], []
            for r, cells in trial.items():
                for c, x, _ in cells:
                    src.append([1.0, c, r])
                    dstx.append(x)
            coef = np.linalg.lstsq(np.array(src), np.array(dstx), rcond=None)[0]
            residual = float(np.max(
                np.abs(coef[0] + coef[1] * np.array([s[1] for s in src])
                       + coef[2] * np.array([s[2] for s in src])
                       - np.array(dstx))))
            if best_residual is None or residual < best_residual:
                best_residual = residual
                assigned = trial
    if assigned is None:
        raise SystemExit("no complete row detected; lattice seeding unreliable")
    # x = a + b*c + s*r fitted on all assigned cells; y = a + b*r on row means.
    src, dstx = [], []
    for r, cells in assigned.items():
        for c, x, _ in cells:
            src.append([1.0, c, r])
            dstx.append(x)
    coef = np.linalg.lstsq(np.array(src), np.array(dstx), rcond=None)[0]
    # Residual guard: the chosen column set must fit the row x-model tightly.
    diffs = [b[0] - a[0]
             for cells in rows.values()
             for a, b in zip(sorted(cells), sorted(cells)[1:])]
    pitch = float(np.median(diffs))
    for r, cells in assigned.items():
        for c, x, _ in cells:
            if abs(coef[0] + coef[1] * c + coef[2] * r - x) > 0.5 * pitch:
                raise SystemExit("column assignment residual too large; "
                                 "lattice seeding unreliable")
    ysrc = np.array([[1.0, r] for r, cells in rows.items() for _ in cells])
    ydst = np.array([y for _, cells in rows.items() for (_, y) in cells])
    ycoef = np.linalg.lstsq(ysrc, ydst, rcond=None)[0]
    pred = {}
    for r in range(base.ROWS):
        for c in range(base.COLS):
            pred[(r, c)] = np.array([coef[0] + coef[1] * c + coef[2] * r,
                                     ycoef[0] + ycoef[1] * r])
    lattice, used = {}, set()
    keys = sorted(pred)
    flat = np.array([pred[k] for k in keys])
    d = np.sqrt(((rc[:, None, :] - flat[None, :, :]) ** 2).sum(axis=2))
    for i in np.argsort(d.min(axis=1)):
        j = int(np.argmin(d[i]))
        if d[i, j] > 45 or j in used:
            continue
        used.add(j)
        lattice[keys[j]] = (float(centers[i, 0]), float(centers[i, 1]))
    if len(lattice) < MIN_ROW_CELLS * base.ROWS:
        raise SystemExit(f"dose lattice fit collapsed: {len(lattice)} cells")
    rows_seen = {r for r, _ in lattice}
    cols_seen = {c for _, c in lattice}
    if len(rows_seen) != base.ROWS or len(cols_seen) < MIN_ROW_CELLS or 0 not in cols_seen:
        raise SystemExit("dose lattice edge rows or dark anchor columns missing")
    return lattice, theta


def apply_central_fraction(value):
    if value is None:
        return
    if type(value) is not float or not 0.2 <= value <= 1.0:
        raise SystemExit("central fraction must be in [0.2, 1.0]")
    base.CENTRAL_FRACTION = value


def recipe_cell(recipe_id: str) -> tuple[int, int]:
    m = RECIPE.fullmatch(recipe_id)
    if not m:
        raise SystemExit(f"recipe id malformed: {recipe_id}")
    return int(m.group(1)), int(m.group(2))


def validate_blank(entries):
    """Pin every blank observation to the dose grid; returns checked entries."""
    if len(entries) != 128:
        raise SystemExit("128 blank observations required")
    for e in entries:
        roi = e["roi"]
        col = (roi["x"] - base.GRID_X0) // (base.CELL_W + base.GAP)
        row = (roi["y"] - base.GRID_Y0) // (base.CELL_H + base.GAP)
        if (roi["x"] - base.GRID_X0) % (base.CELL_W + base.GAP) or \
                (roi["y"] - base.GRID_Y0) % (base.CELL_H + base.GAP):
            raise SystemExit("blank ROI off grid")
        code, r = recipe_cell(e["recipe_id"])
        if code != col or r != row:
            raise SystemExit(
                f"blank recipe/grid mismatch at {e['controller']} r{row} c{col}")
        if e["comparison_id"] != f"{COMPARISON_PREFIX}{code}":
            raise SystemExit(
                f"comparison_id mismatch at {e['controller']} r{row} c{col}")
    return entries


def stage_identity(blank, contract, stage, live_result):
    """Build the extraction identity for one dose stage; pure checks, no I/O.

    The two dose frames are byte-identical, so the stage binds through the
    contract action id; the live device result must independently agree.
    """
    action = contract["actions"][STAGE_ORDINAL[stage] - 1]
    if action["stage"] != stage:
        raise SystemExit("contract stage/action mismatch")
    if live_result.get("kind") != RESULT_KIND or \
            live_result.get("protocol_verdict") != "PASS":
        raise SystemExit("live result is not a PASS result")
    report = live_result.get("report", {})
    if live_result.get("ordinal") != STAGE_ORDINAL[stage] or \
            report.get("action_id") != action["action_id"] or \
            report.get("descriptor_id") != action["descriptor_id"] or \
            report.get("terminal_state") != "COMPLETE" or \
            report.get("result") is not True:
        raise SystemExit(f"live result does not bind the contract {stage} action")
    if live_result.get("contract_id") != contract["contract_id"] or \
            report.get("contract_id") != contract["contract_id"]:
        raise SystemExit("live result contract differs")
    boot = live_result.get("boot_nonce")
    if not isinstance(boot, str) or not re.fullmatch(r"[0-9a-f]{16}", boot):
        raise SystemExit("live result boot nonce malformed")
    identity = dict(blank["identity"])
    identity["action_sha256"] = action["action_id"]
    if identity.get("frame_sha256") != action["frame"]["sha256"]:
        raise SystemExit("blank identity frame sha does not bind the stage frame")
    if identity.get("profile_id") != action["profile_id"]:
        raise SystemExit("blank identity profile differs")
    identity["contract_id"] = contract["contract_id"]
    identity["stage"] = stage
    identity["boot_nonce"] = boot
    identity["run_id"] = live_result.get("run_id")
    identity["campaign_complete"] = live_result.get("campaign_complete")
    return identity, action


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frames-dir", type=Path, required=True,
                   help="directory with exactly 10 same-state frames + sidecars")
    p.add_argument("--stage", choices=tuple(STAGE_ORDINAL), required=True)
    p.add_argument("--package", type=Path, required=True,
                   help="sealed LH3 dose package (observations.blank.json, contract.json)")
    p.add_argument("--live-result", type=Path, required=True,
                   help="sealed live-sN/result.json of this stage")
    p.add_argument("--middle-extraction", type=Path, required=True,
                   help="sealed MIDDLE extraction.json carrying the solved mapping")
    p.add_argument("--anchor-frame", type=Path, default=None,
                   help="optional 11th same-state capture sampled as re-test")
    p.add_argument("--central-fraction", type=float, default=None,
                   help="override the sampled central fraction of each cell "
                        "(default 0.6; smaller insets exclude the cell edge "
                        "transition band; the value is recorded in the "
                        "extraction report)")
    p.add_argument("--output", type=Path, required=True,
                   help="extraction JSON path (must not exist)")
    args = p.parse_args()
    apply_central_fraction(args.central_fraction)
    if args.output.exists():
        raise SystemExit("output file must not exist (O_EXCL batch)")

    live_result = json.loads(args.live_result.read_text(encoding="utf-8"))
    middle_sha = base.sha256(args.middle_extraction.read_bytes())
    mapping = load_middle_mapping(args.middle_extraction)
    blank = json.loads((args.package / "observations.blank.json").read_text(encoding="utf-8"))
    entries = validate_blank(blank["observations"])
    contract = json.loads((args.package / "contract.json").read_text(encoding="utf-8"))
    identity, action = stage_identity(blank, contract, args.stage, live_result)

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
    comps = grid_components(detect_centers(bgr0))
    side_of = {"left": comps[0] if comps[0][:, 0].mean() < comps[1][:, 0].mean() else comps[1],
               "right": comps[1] if comps[0][:, 0].mean() < comps[1][:, 0].mean() else comps[0]}
    lattices = {}
    for side, pts in side_of.items():
        lattices[side], _ = assign_dose_lattice(pts)
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
        comps_f = grid_components(detect_centers(bgr))
        sides = {"left": comps_f[0] if comps_f[0][:, 0].mean() < comps_f[1][:, 0].mean() else comps_f[1],
                 "right": comps_f[1] if comps_f[0][:, 0].mean() < comps_f[1][:, 0].mean() else comps_f[0]}
        rep = {"frame": frame_name}
        homographies = {}
        for side, pts in sides.items():
            claims: dict = {}
            ref = reference_centers[side]
            ref_keys = sorted(ref)
            ref_pts = np.array([ref[k] for k in ref_keys])
            for x, y in pts:
                d = np.sqrt(((ref_pts - (x, y)) ** 2).sum(axis=1))
                j = int(np.argmin(d))
                if d[j] > 40:
                    raise SystemExit(f"{frame_name} {side}: unmatched cell at {(x, y)}")
                claims.setdefault(ref_keys[j], []).append((float(x), float(y)))
            # Ambiguous keys (two detected centres within one cell's match
            # radius, e.g. a specular spot on the dim 2026-09-24 session) are
            # excluded from the fit entirely; their position comes from the
            # homography, exactly like undetected near-white cells.
            lattice = {key: xy[0] for key, xy in claims.items() if len(xy) == 1}
            ambiguous = {key for key, xy in claims.items() if len(xy) != 1}
            if len(lattice) < MIN_COMPONENT_CELLS:
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
                                       "ambiguous_assignment_cells_excluded": sorted(
                                           [list(k) for k in ambiguous]),
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
        code, _r = recipe_cell(e["recipe_id"])
        row = {"entry": i, "recipe_id": e["recipe_id"], "controller": e["controller"],
               "position": e["position"], "comparison_id": e["comparison_id"],
               "dose_code": code, "grid_row": row_l, "grid_col": col_l,
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
    report = {"kind": EXTRACTION_KIND,
              "identity": identity, "analyzer_version": ANALYZER_VERSION,
              "assignment_scatter_limit_px": ASSIGNMENT_SCATTER_LIMIT_PX,
              "placement_crosscheck": "PASS",
              "lab_crosscheck_max_abs": lab_crosscheck_max_abs,
              "mapping_source": {"inherited_from_sealed_middle_extraction": True,
                                 "middle_extraction_path": str(args.middle_extraction),
                                 "middle_extraction_sha256": middle_sha,
                                 "mapping": mapping},
              STAGE_CONTRACT_KEY: {"contract_id": contract["contract_id"],
                                      "stage": args.stage,
                                      "action_sha256": action["action_id"],
                                      "frame_sha256": action["frame"]["sha256"],
                                      "frame_histogram": action["frame"]["histogram"]},
              "live_result": {"path": str(args.live_result.resolve()),
                              "sha256": base.sha256(args.live_result.read_bytes())},
              "cell_detection": {"method": "morphological-blackhat",
                                 "reason": "2026-09-24 session is dim (monitor off) and the camera moved slightly (keyboard in frame); fixed-threshold masks would select the whole scene",
                                 "kernel_px": map_analyzer.BLACKHAT_KERNEL_PX,
                                 "threshold_sum": map_analyzer.BLACKHAT_THRESHOLD},
              "roi_sampling": {"central_fraction": float(base.CENTRAL_FRACTION),
                               "note": "fraction of each cell's width/height "
                                       "sampled around its centre; the rest is "
                                       "the edge transition band"},
              "anchor_frame": {"path": str(args.anchor_frame),
                               "sha256": base.sha256(args.anchor_frame.read_bytes()),
                               "report": anchor_report} if args.anchor_frame else None,
              "frames": frame_reports, "rows": rows}
    sealed = attach_integrity(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(sealed, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output),
                      "lab_crosscheck_max_abs": lab_crosscheck_max_abs,
                      "mapping": mapping, "frames": len(frames), "stage": args.stage,
                      "anchor": args.anchor_frame.name if args.anchor_frame else None},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
