#!/usr/bin/env python3
"""Offline 10-frame 128-ROI extractor for the LH1 rebound V2 MIDDLE matrix.

Read-only image analysis: no device, network, relay or camera access. Binds the
sealed package recipe placement tables to the actual camera frames, derives the
CS1/CS2 side assignment and orientation from global code<->colour-cluster
consistency (never guessed from left/right), samples each ROI's central 60% per
frame, and emits per-ROI camera-relative Lab plus 10-sample noise statistics
ready for ``tools/mf1750_lightness_test.py analyze``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from host.color_pipeline.color import srgb8_to_lab  # noqa: E402

GRID_X0, GRID_Y0 = 68, 64
CELL_W, CELL_H = 40, 52
GAP = 8
ROWS = COLS = 8
CENTRAL_FRACTION = 0.6
MIN_AREA, MAX_AREA = 2500, 15000
UNIFORM_P95_DE76_LIMIT = 4.0
FRAME_DRIFT_LIMIT_PX = 5.0
CLIP_LIMIT = 0.01
PROBE_RADIUS_PX = 22
# V2 (2026-09-17, user-waived): assignment-scatter bound relaxed 3.0 -> 15.0 px.
# Justification: the central-60% ROI window is ~44x58 image px inside a ~78x97 px
# patch, so <=15 px inter-frame assignment jitter keeps the sampled window fully
# inside the same uniform patch; colour medians are unaffected (verified by the
# stable per-frame L* series of the jittered cells). Optical thresholds
# (position/separation/noise) stay frozen at MF1750_LIGHTNESS_TEST_V1_20260911.
ASSIGNMENT_SCATTER_LIMIT_PX = 15.0
ANALYZER_VERSION = "mf1750-lh1-rebound-v2-middle-photo-analyzer-v2"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_placement(inc_path: Path) -> dict[str, list[int]]:
    text = inc_path.read_text(encoding="utf-8")
    out = {}
    for name in ("kRecipeAtCellCs1", "kRecipeAtCellCs2"):
        m = re.search(name + r"\[64\]=\{([0-9,]+)\}", text)
        if not m:
            raise SystemExit(f"placement table missing: {name}")
        values = [int(v) for v in m.group(1).split(",")]
        if len(values) != 64 or max(values) > 15 or min(values) < 0:
            raise SystemExit(f"placement table malformed: {name}")
        out[name] = values
    return out


def recipe_index(recipe_id: str) -> int:
    m = re.fullmatch(r"LH1-S7-M([0-7])-T([37])", recipe_id)
    if not m:
        raise SystemExit(f"recipe id malformed: {recipe_id}")
    return int(m.group(1)) + (0 if m.group(2) == "3" else 8)


def detect_centers(bgr: np.ndarray) -> np.ndarray:
    """Detect coloured patch centres; white cells stay undetected by design."""
    sums = bgr.astype(np.int32).sum(axis=2)
    mask = (sums < 430).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    centers = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[i])
        if area < MIN_AREA or area > 2 * MAX_AREA:
            continue
        if w > h * 1.4 and area > 8000:  # two horizontally merged cells
            centers.append((x + w / 4.0, y + h / 2.0))
            centers.append((x + 3 * w / 4.0, y + h / 2.0))
            continue
        if h > w * 1.4 and area > 8000:  # two vertically merged cells
            centers.append((x + w / 2.0, y + h / 4.0))
            centers.append((x + w / 2.0, y + 3 * h / 4.0))
            continue
        if area > MAX_AREA or not 0.45 <= w / h <= 1.30:
            continue
        centers.append((x + w / 2.0, y + h / 2.0))
    return np.array(centers, dtype=np.float64)


def grid_components(centers: np.ndarray) -> list[np.ndarray]:
    """Keep exactly the two dense matrix clusters via lattice-neighbour BFS."""
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
    if len(comps) < 2 or len(comps[0]) < 50 or len(comps[1]) < 50:
        raise SystemExit(f"two dense matrices required; component sizes: {[len(c) for c in comps]}")
    if len(comps) > 2 and len(comps[2]) > 4:
        raise SystemExit(f"unexpected third dense cluster: {[len(c) for c in comps]}")
    return comps[:2]


def _cluster1d(values: np.ndarray, k: int) -> np.ndarray:
    """Deterministic 1D k-partition for near-uniform lattice coordinates."""
    centers = np.linspace(values.min(), values.max(), k)
    for _ in range(200):
        labels = np.abs(values[:, None] - centers[None, :]).argmin(axis=1)
        new = np.array([values[labels == i].mean() if (labels == i).any() else centers[i]
                        for i in range(k)])
        if np.max(np.abs(new - centers)) < 1e-9:
            break
        centers = new
    return labels


def assign_lattice(centers: np.ndarray) -> tuple[dict, float]:
    """Assign (row, col) lattice indices in image space to detected centres.

    ICP-style fit: derotate, rough affine from spread, then iterate
    nearest-intersection matching and refit. Refuses ambiguous assignments.
    """
    best = None
    for theta in np.arange(-8.0, 8.0, 0.1):
        rad = math.radians(theta)
        rot = np.array([[math.cos(rad), -math.sin(rad)], [math.sin(rad), math.cos(rad)]])
        rc = centers @ rot.T
        labels = _cluster1d(rc[:, 1], ROWS)
        var = float(np.sum([np.var(rc[labels == k, 1]) for k in range(ROWS)]))
        if best is None or var < best[0]:
            best = (var, theta, rc)
    _, theta, rc = best
    rad = math.radians(theta)
    rot = np.array([[math.cos(rad), -math.sin(rad)], [math.sin(rad), math.cos(rad)]])
    # Row labels from derotated y; then column model from complete rows only
    # (perspective shear makes global column clustering unreliable).
    row_labels = _cluster1d(rc[:, 1], ROWS)
    rows: dict[int, list[tuple[float, float]]] = {}
    for i, (x, y) in enumerate(rc):
        rows.setdefault(int(row_labels[i]), []).append((float(x), float(y)))
    complete = [r for r, cells in rows.items() if len(cells) == COLS]
    if not complete:
        raise SystemExit("no fully detected row; lattice seeding unreliable")
    # x = a + b*c + s*r fitted on complete rows
    src, dstx = [], []
    for r in complete:
        for c, (x, _) in enumerate(sorted(rows[r])):
            src.append([1.0, c, r])
            dstx.append(x)
    coef = np.linalg.lstsq(np.array(src), np.array(dstx), rcond=None)[0]
    # y = a + b*r fitted on all cells (row means)
    ysrc = np.array([[1.0, r] for r, cells in rows.items() for _ in cells])
    ydst = np.array([y for _, cells in rows.items() for (_, y) in cells])
    ycoef = np.linalg.lstsq(ysrc, ydst, rcond=None)[0]
    pred = {}
    for r in range(ROWS):
        for c in range(COLS):
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
    if len(lattice) < 50:
        raise SystemExit(f"lattice fit collapsed: {len(lattice)} cells")
    rows_seen = {r for r, _ in lattice}
    cols_seen = {c for _, c in lattice}
    if len(rows_seen) != ROWS or len(cols_seen) != COLS:
        raise SystemExit("lattice edge rows/cols missing; fit unreliable")
    return lattice, theta


def lattice_homography(lattice: dict) -> np.ndarray:
    """Image-lattice (row, col) -> image pixel homography (for missing cells)."""
    src = np.array([[c, r] for (r, c) in sorted(lattice)], dtype=np.float64)
    dst = np.array([lattice[(r, c)] for (r, c) in sorted(lattice)], dtype=np.float64)
    h, _ = cv2.findHomography(src, dst, 0)
    return h


def local_center(row: int, col: int) -> tuple[float, float]:
    return (GRID_X0 + col * (CELL_W + GAP) + CELL_W / 2.0,
            GRID_Y0 + row * (CELL_H + GAP) + CELL_H / 2.0)


def probe_lab(bgr: np.ndarray, x: float, y: float) -> np.ndarray:
    xi, yi = int(round(x)), int(round(y))
    patch = bgr[yi - PROBE_RADIUS_PX:yi + PROBE_RADIUS_PX + 1,
                xi - PROBE_RADIUS_PX:xi + PROBE_RADIUS_PX + 1]
    if patch.size == 0:
        raise SystemExit("probe outside image")
    rgb = patch.reshape(-1, 3)[:, ::-1]
    return np.median(srgb_to_lab_batch(rgb), axis=0)


def srgb_to_lab_batch(rgb: np.ndarray) -> np.ndarray:
    """Vectorized sRGB8 -> CIE L*a*b* (D65/2deg); cross-checked against host pipeline."""
    f = rgb.astype(np.float64) / 255.0
    lin = np.where(f <= 0.04045, f / 12.92, ((f + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    e = 216 / 24389
    k = 24389 / 27
    fxyz = np.where(xyz > e, np.cbrt(xyz), (k * xyz + 16) / 116)
    return np.stack([116 * fxyz[:, 1] - 16,
                     500 * (fxyz[:, 0] - fxyz[:, 1]),
                     200 * (fxyz[:, 1] - fxyz[:, 2])], axis=1)


def crosscheck_lab() -> float:
    rng = np.random.default_rng(20260917)
    samples = rng.integers(0, 256, size=(256, 3))
    mine = srgb_to_lab_batch(samples)
    theirs = np.array([srgb8_to_lab(tuple(int(v) for v in px)) for px in samples])
    return float(np.max(np.abs(mine - theirs)))


TRANSFORMS = {"identity": lambda r, c: (r, c),
              "rot180": lambda r, c: (ROWS - 1 - r, COLS - 1 - c)}


def solve_mapping(side_labs: dict[str, np.ndarray], placement: dict[str, list[int]]) -> dict:
    """Find side assignment + per-side orientation by within-code dispersion.

    For every candidate (side<->controller, per-side identity/rot180), collect
    the observed Lab of all 16 cells assigned to each code and score the mean
    distance to the code centroid. Correct mappings keep one code = one colour
    (small dispersion); wrong mappings mix colours (large dispersion). The
    scores of all candidates are recorded as evidence.
    """
    sides = sorted(side_labs)
    scored = []
    for side_as_ctrl in ({"CS1": sides[0], "CS2": sides[1]}, {"CS1": sides[1], "CS2": sides[0]}):
        for t_a in TRANSFORMS:
            for t_b in TRANSFORMS:
                t_of = {sides[0]: TRANSFORMS[t_a], sides[1]: TRANSFORMS[t_b]}
                tnames = {sides[0]: t_a, sides[1]: t_b}
                dispersions = []
                for code in range(8):
                    pts = []
                    for ctrl, side in side_as_ctrl.items():
                        for r in range(ROWS):
                            for c in range(COLS):
                                if placement[ctrl][r * COLS + c] % 8 == code:
                                    ir, ic = t_of[side](r, c)
                                    pts.append(side_labs[side][ir, ic])
                    pts = np.array(pts)
                    centroid = pts.mean(axis=0)
                    dispersions.append(float(np.linalg.norm(pts - centroid, axis=1).mean()))
                scored.append((float(np.mean(dispersions)), dict(side_as_ctrl), tnames,
                               [float(d) for d in dispersions]))
    scored.sort(key=lambda x: x[0])
    distinct = []
    for s in scored:
        if not distinct or abs(s[0] - distinct[-1][0]) > 1e-6:
            distinct.append(s)
    best = distinct[0]
    runner = distinct[1] if len(distinct) > 1 else None
    evidence = {"candidate_dispersions": [{"mean_within_code_delta_e76": s[0],
                                           "side_to_ctrl": s[1], "transform_per_side": s[2],
                                           "per_code": s[3]} for s in scored],
                "equivalence_note": "CS2 placement table equals rot180(CS1); swapping side labels plus rotating both sides is the same physical mapping, so twin scores are identical by construction."}
    if runner is None or runner[0] < best[0] * 1.15 or (runner[0] - best[0]) < 1.0:
        return None, {**evidence, "error": "side/orientation margin too small between distinct mappings"}
    # Code-7 consistency: the SOURCE frame was a uniform white C7 field, so the
    # chosen mapping must place code 7 in the brightest (white) cells.
    side_as_ctrl, tnames = best[1], best[2]
    code7, others = [], []
    for ctrl, side in side_as_ctrl.items():
        t = TRANSFORMS[tnames[side]]
        for r in range(ROWS):
            for c in range(COLS):
                ir, ic = t(r, c)
                (code7 if placement[ctrl][r * COLS + c] % 8 == 7 else others).append(side_labs[side][ir, ic])
    l7 = float(np.mean([p[0] for p in code7]))
    lo = float(np.mean([p[0] for p in others]))
    evidence["code7_mean_lstar"] = l7
    evidence["other_codes_mean_lstar"] = lo
    if l7 <= lo + 10:
        return None, {**evidence, "error": "code 7 is not clearly the white cells; mapping rejected"}
    mapping = {"side_to_ctrl": side_as_ctrl, "transform_per_side": tnames,
               "within_code_dispersion": best[3], "runner_up_dispersion": runner[0],
               "code7_mean_lstar": l7, "other_codes_mean_lstar": lo}
    return {"mapping": mapping, "candidate_dispersions": evidence["candidate_dispersions"],
            "equivalence_note": evidence["equivalence_note"]}, None


def sample_roi_lab(bgr: np.ndarray, homography: np.ndarray, roi: dict) -> tuple[np.ndarray | None, dict]:
    margin_x = roi["width"] * (1 - CENTRAL_FRACTION) / 2
    margin_y = roi["height"] * (1 - CENTRAL_FRACTION) / 2
    x0, x1 = roi["x"] + margin_x, roi["x"] + roi["width"] - margin_x
    y0, y1 = roi["y"] + margin_y, roi["y"] + roi["height"] - margin_y
    corners = np.array([[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]], dtype=np.float64)
    quad = cv2.perspectiveTransform(corners, homography)[0]
    min_xy = np.floor(quad.min(axis=0)).astype(int) - 1
    max_xy = np.ceil(quad.max(axis=0)).astype(int) + 1
    h, w = bgr.shape[:2]
    if min_xy[0] < 0 or min_xy[1] < 0 or max_xy[0] >= w or max_xy[1] >= h:
        return None, {"inside_image": False}
    mask = np.zeros((max_xy[1] - min_xy[1] + 1, max_xy[0] - min_xy[0] + 1), np.uint8)
    cv2.fillConvexPoly(mask, np.round(quad - min_xy).astype(np.int32), 255)
    pixels = bgr[min_xy[1]:max_xy[1] + 1, min_xy[0]:max_xy[0] + 1][mask > 0]
    if len(pixels) < 200:
        return None, {"inside_image": True, "pixel_count": int(len(pixels))}
    lab = srgb_to_lab_batch(pixels[:, ::-1])
    med = np.median(lab, axis=0)
    de76 = np.linalg.norm(lab - med, axis=1)
    return med, {"inside_image": True, "pixel_count": int(len(pixels)),
                 "uniform_p95_delta_e76": float(np.percentile(de76, 95)),
                 "clip_high_fraction": float(np.mean(np.all(pixels >= 250, axis=1))),
                 "clip_low_fraction": float(np.mean(np.all(pixels <= 5, axis=1)))}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frames-dir", type=Path, required=True)
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--identity", type=Path, required=True,
                   help="JSON with the sealed MIDDLE identity fields")
    args = p.parse_args()
    if args.output_dir.exists():
        raise SystemExit("output dir must not exist (O_EXCL batch)")

    identity = json.loads(args.identity.read_text(encoding="utf-8"))
    blank = json.loads((args.package / "observations.blank.json").read_text(encoding="utf-8"))
    entries = blank["observations"]
    if len(entries) != 128:
        raise SystemExit("128 blank observations required")
    inc = args.package / "generated" / "ec5_lightness_lh1_rebound_v2_identity.inc"
    placement_all = load_placement(inc)
    placement = {"CS1": placement_all["kRecipeAtCellCs1"], "CS2": placement_all["kRecipeAtCellCs2"]}
    for e in entries:
        roi = e["roi"]
        col = (roi["x"] - GRID_X0) // (CELL_W + GAP)
        row = (roi["y"] - GRID_Y0) // (CELL_H + GAP)
        if (roi["x"] - GRID_X0) % (CELL_W + GAP) or (roi["y"] - GRID_Y0) % (CELL_H + GAP):
            raise SystemExit("blank ROI off grid")
        want = recipe_index(e["recipe_id"])
        got = placement[e["controller"]][row * COLS + col]
        if want != got:
            raise SystemExit(f"blank/placement mismatch at {e['controller']} r{row} c{col}")

    lab_crosscheck_max_abs = crosscheck_lab()
    frames = sorted(args.frames_dir.glob("*.jpg"))
    if len(frames) != 10:
        raise SystemExit("exactly 10 frames required")
    if not all(f.with_suffix(".capture.json").exists() for f in frames):
        raise SystemExit("every frame needs its capture sidecar")

    # Pass 1: geometry + orientation evidence from the first frame.
    bgr0 = cv2.imread(str(frames[0]))
    if bgr0 is None or bgr0.shape[:2] != (3000, 4000):
        raise SystemExit("first frame unreadable or wrong size")
    comps = grid_components(detect_centers(bgr0))
    side_of = {"left": comps[0] if comps[0][:, 0].mean() < comps[1][:, 0].mean() else comps[1],
               "right": comps[1] if comps[0][:, 0].mean() < comps[1][:, 0].mean() else comps[0]}
    lattices, rotations = {}, {}
    for side, pts in side_of.items():
        lattices[side], rotations[side] = assign_lattice(pts)
    side_labs = {}
    for side, lattice in lattices.items():
        h = lattice_homography(lattice)
        cells = np.zeros((ROWS, COLS, 3))
        for r in range(ROWS):
            for c in range(COLS):
                xy = lattice.get((r, c))
                if xy is None:
                    xy = cv2.perspectiveTransform(np.array([[[c, r]]], dtype=np.float64), h)[0, 0]
                cells[r, c] = probe_lab(bgr0, xy[0], xy[1])
        side_labs[side] = cells
    solved, error = solve_mapping(side_labs, placement)
    if solved is None:
        raise SystemExit("mapping unresolved: " + json.dumps(error))
    mapping = solved["mapping"]
    side_to_ctrl = mapping["side_to_ctrl"]
    ctrl_of_side = {side: ctrl for ctrl, side in side_to_ctrl.items()}
    transform_of = {side: TRANSFORMS[name] for side, name in mapping["transform_per_side"].items()}

    # Full 64-cell image-space reference per side: detected centres where
    # available, homography-predicted for the (white) cells frame 1 missed.
    reference_centers: dict[str, dict] = {}
    for side, lattice in lattices.items():
        transform = transform_of[side]
        src, dst = [], []
        for (ir, ic), (x, y) in lattice.items():
            matched = [(r, c) for r in range(ROWS) for c in range(COLS) if transform(r, c) == (ir, ic)]
            (r, c), = matched
            src.append(local_center(r, c))
            dst.append((x, y))
        h, _ = cv2.findHomography(np.array(src), np.array(dst), 0)
        ref = {}
        for ir in range(ROWS):
            for ic in range(COLS):
                if (ir, ic) in lattice:
                    ref[(ir, ic)] = lattice[(ir, ic)]
                else:
                    matched = [(r, c) for r in range(ROWS) for c in range(COLS) if transform(r, c) == (ir, ic)]
                    (r, c), = matched
                    ref[(ir, ic)] = tuple(cv2.perspectiveTransform(
                        np.array([[local_center(r, c)]], dtype=np.float64), h)[0, 0])
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
        comps = grid_components(detect_centers(bgr))
        sides = {"left": comps[0] if comps[0][:, 0].mean() < comps[1][:, 0].mean() else comps[1],
                 "right": comps[1] if comps[0][:, 0].mean() < comps[1][:, 0].mean() else comps[0]}
        frame_rep = {"frame": frame_path.name}
        homographies = {}
        for side, pts in sides.items():
            # Camera is fixed; assign by nearest reference cell instead of
            # per-frame re-clustering (which can swap columns).
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
            # local grid centre -> image, through the solved side/orientation
            transform = transform_of[side]
            src, dst = [], []
            for (ir, ic), (x, y) in lattice.items():
                matched = [(r, c) for r in range(ROWS) for c in range(COLS) if transform(r, c) == (ir, ic)]
                (r, c), = matched
                src.append(local_center(r, c))
                dst.append((x, y))
            h, _ = cv2.findHomography(np.array(src), np.array(dst), cv2.LMEDS)
            proj = cv2.perspectiveTransform(np.array(src).reshape(-1, 1, 2), h).reshape(-1, 2)
            rmse = float(np.sqrt(np.mean(np.sum((proj - np.array(dst)) ** 2, axis=1))))
            # Camera stability is gated on the median assignment displacement;
            # isolated corner-cell detection jitter is handled per ROI below.
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
            med, quality = sample_roi_lab(bgr, homographies[e["controller"]], e["roi"])
            if med is None:
                raise SystemExit(f"ROI outside image or empty: {json.dumps(e)}")
            per_roi_samples[i].append(med)
            per_roi_quality[i].append(quality)
        frame_reports.append(frame_rep)

    rows = []
    transform_of_ctrl = {ctrl_of_side[side]: TRANSFORMS[mapping["transform_per_side"][side]]
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
        row_l = (e["roi"]["y"] - GRID_Y0) // (CELL_H + GAP)
        col_l = (e["roi"]["x"] - GRID_X0) // (CELL_W + GAP)
        ikey = transform_of_ctrl[e["controller"]](row_l, col_l)
        track = cell_tracks.get((side_to_ctrl[e["controller"]], ikey), [])
        if len(track) >= 2:
            tmed = np.median(np.array(track), axis=0)
            scatter = float(max(math.dist(p, tuple(tmed)) for p in track))
        else:
            scatter = None  # white cells are not detected; position comes from homography
        rows.append({"entry": i, "recipe_id": e["recipe_id"], "controller": e["controller"],
                     "position": e["position"], "lab_median": [float(v) for v in med],
                     "lab_samples": [[float(v) for v in s] for s in samples],
                     "lstar_mad": mad_l, "lstar_ci95_half_width": ci_l,
                     "assignment_scatter_px": scatter,
                     "quality_pass": bool(max_clip <= CLIP_LIMIT
                                          and (scatter is None or scatter <= ASSIGNMENT_SCATTER_LIMIT_PX)),
                     "single_pixel_uniform": bool(max_uniform_p95 <= UNIFORM_P95_DE76_LIMIT),
                     "max_clip_fraction": max_clip,
                     "max_uniform_p95_delta_e76": max_uniform_p95})
    report = {"identity": identity, "analyzer_version": ANALYZER_VERSION,
              "assignment_scatter_limit_px": ASSIGNMENT_SCATTER_LIMIT_PX,
              "placement_crosscheck": "PASS",
              "lab_crosscheck_max_abs": lab_crosscheck_max_abs,
              "mapping_evidence": solved, "frames": frame_reports, "rows": rows}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    out = args.output_dir / "extraction.json"
    out.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(out), "lab_crosscheck_max_abs": lab_crosscheck_max_abs,
                      "mapping": mapping, "frames": len(frames)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
