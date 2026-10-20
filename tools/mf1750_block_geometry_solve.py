#!/usr/bin/env python3
"""Solve content->photo homography from known atlas blocks and measure 8-code Lab.

P0V4 post-batch one-shot pipeline (offline, no device/camera/network access).
The camera framing gate (amendment 3) forbids relying on panel corners in
frame, so the displayed blocks themselves are the fiducials: the roi-list
pins every block's content rectangle at compile time.

Method (generalized from the V3 recon arbitration, whose solve script and
final H live in .test-output/offline/PARTIAL_BLOCK_P0V3_GEOMETRY_20261020_V1/
solve_geometry.py and geometry-unflipped-A.json):
  1. Detect visible block quads: absdiff against a white-field photo when
     --white-photo is given (camera batch-internal zero drift), else color
     distance from the photo's median background.  Blobs touching a photo
     border with a full edge are classed as truncated slivers and are excluded
     from the fit (V3 sliver lesson); they are matched post-hoc.
  2. Brute-force assignment of full blobs to content rects, scored by corner
     reprojection RMS with per-blob roll search (k<=3: all roll combinations
     enumerated; k>=4: centroid-seeded iteration; k>=5: centroid-prefiltered
     top-256 hypotheses).  Panel-edge artifacts are suppressed by area and
     quad-conformity filters.  code1/code7-style invisible blocks are simply
     never detected and are reported in the missing list; the solver only
     uses detected blocks.  Symmetric occupancies (e.g. code7 invisible) tie
     exactly — the V3 arbitration lesson; ties are broken by the rim anchor
     only when it clearly discriminates (factor-2 margin), otherwise they are
     reported and the assignment is marked reliable=false.
  3. Optional rim anchor: with --rim-photo (white-field photo with the bright
     active area against dark surround) the active-area quad is detected with
     two-stage Otsu and rim_err is the mean distance of the projected content
     x=0 line to the rim quad's photo-left vertical edge (rig convention, same
     anchor as the V3 arbitration).
  4. Lab handoff: the photo (and white photo, if given) are warped back to the
     1024x600 content plane via H^-1 and measured with
     tools/mf1750_multi_roi_lab.py (batch white-field delta convention),
     writing lab-report.json + lab-annotated.png into the output directory.

Outputs (all created exclusively; the output directory must not exist):
  geometry.json   sealed report (sha256-canonical-json-without-integrity,
                  same convention as tools/mf1750_wmask_atlas.py)
  overlay.jpg     detected quads + predicted rects + rim overlay
  warped.png      photo rectified to the content plane
  white-warped.png / lab-report.json / lab-annotated.png  (Lab stage)

Usage:
  python tools/mf1750_block_geometry_solve.py \
      --photo 05-atlas-t0.jpg \
      --roi-list .test-output/offline/MF1750_PARTIAL_BLOCK_20261020_V4/partial-atlas-1e-v4-roi-list.json \
      --white-photo 04-postnorm-white.jpg --rim-photo 04-postnorm-white.jpg \
      --output-dir out/P0V4_ANALYSIS
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import itertools
import json
import math
from pathlib import Path
import stat
import sys
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import mf1750_multi_roi_lab as roi_lab  # noqa: E402

SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 600
DEFAULT_DIFF_THRESHOLD = 15.0
DEFAULT_MIN_BLOB_AREA = 500
BORDER_PX = 6
RIM_SAMPLE_POINTS = 40
TRUNCATED_MATCH_MAX_DIST = 200.0
REPORT_KIND = "mf1750-block-geometry-solve"


class GeometrySolveError(ValueError):
    """Raised for invalid inputs, failed detection, or unsolvable geometry."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _pretty(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(payload)


def _file_record(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "name": path.name,
        "bytes": len(payload),
        "sha256": _sha256(payload),
    }


def _read_image(path: Path, *, label: str) -> tuple[bytes, np.ndarray]:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise GeometrySolveError(f"{label} must be a regular non-symlink")
        payload = path.read_bytes()
    except OSError as error:
        raise GeometrySolveError(f"{label} cannot be read: {error}") from error
    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise GeometrySolveError(f"{label} is not a supported three-channel image")
    if image.shape[0] < 200 or image.shape[1] < 200:
        raise GeometrySolveError(f"{label} is too small")
    return payload, image


def _load_roi_list(path: Path) -> tuple[list[dict[str, Any]], bytes, str | None]:
    payload = path.read_bytes()
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GeometrySolveError(f"roi-list is not UTF-8 JSON: {error}") from error
    if not isinstance(document, dict) or not isinstance(document.get("regions"), list):
        raise GeometrySolveError("roi-list must be an object with a regions array")
    screen = document.get("screen")
    if screen is not None and (
        not isinstance(screen, Mapping)
        or screen.get("width") != SCREEN_WIDTH
        or screen.get("height") != SCREEN_HEIGHT
    ):
        raise GeometrySolveError(
            f"roi-list screen must be {SCREEN_WIDTH}x{SCREEN_HEIGHT} when declared"
        )
    regions: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, raw in enumerate(document["regions"]):
        if not isinstance(raw, Mapping):
            raise GeometrySolveError(f"roi-list region {index} must be an object")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise GeometrySolveError(f"roi-list region {index} requires a name")
        if name in names:
            raise GeometrySolveError(f"duplicate roi-list region name {name!r}")
        names.add(name)
        values: dict[str, float] = {}
        for key in ("x", "y", "w", "h"):
            value = raw.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise GeometrySolveError(f"roi-list region {name!r} requires numeric {key}")
            values[key] = float(value)
        if values["w"] < 10 or values["h"] < 10:
            raise GeometrySolveError(f"roi-list region {name!r} is smaller than 10x10")
        if (
            values["x"] < 0
            or values["y"] < 0
            or values["x"] + values["w"] > SCREEN_WIDTH
            or values["y"] + values["h"] > SCREEN_HEIGHT
        ):
            raise GeometrySolveError(f"roi-list region {name!r} escapes the screen")
        code = raw.get("code")
        if code is not None and (isinstance(code, bool) or not isinstance(code, (int, str))):
            raise GeometrySolveError(f"roi-list region {name!r} code must be int, str, or null")
        regions.append({"name": name, "code": code, **values})
    if len(regions) < 3:
        raise GeometrySolveError("roi-list must contain at least 3 regions")
    revision = document.get("layout_revision")
    return regions, payload, revision if isinstance(revision, str) else None


def _rect_corners(region: Mapping[str, Any]) -> np.ndarray:
    x, y, w, h = region["x"], region["y"], region["w"], region["h"]
    return np.array(
        [(x, y), (x + w, y), (x + w, y + h), (x, y + h)], dtype=np.float64
    )


def _rect_center(region: Mapping[str, Any]) -> np.ndarray:
    return np.array(
        [region["x"] + region["w"] / 2.0, region["y"] + region["h"] / 2.0],
        dtype=np.float64,
    )


def _order_quad(box: np.ndarray) -> np.ndarray:
    """Order quad corners TL, TR, BR, BL (visual frame), counter-clockwise."""
    center = box.mean(axis=0)
    angles = np.arctan2(box[:, 1] - center[1], box[:, 0] - center[0])
    ordered = box[np.argsort(angles)]
    start = int(np.argmin(ordered[:, 0] + ordered[:, 1]))
    return np.roll(ordered, -start, axis=0).astype(np.float64)


def _truncated_edge(quad: np.ndarray, width: int, height: int) -> str | None:
    """A quad with both endpoints of one edge on a photo border is a sliver."""
    edges = {"top": (0, 1), "right": (1, 2), "bottom": (2, 3), "left": (3, 0)}
    for edge, (a, b) in edges.items():
        if edge == "top" and quad[a][1] <= BORDER_PX and quad[b][1] <= BORDER_PX:
            return "top"
        if edge == "bottom" and quad[a][1] >= height - 1 - BORDER_PX and quad[b][1] >= height - 1 - BORDER_PX:
            return "bottom"
        if edge == "left" and quad[a][0] <= BORDER_PX and quad[b][0] <= BORDER_PX:
            return "left"
        if edge == "right" and quad[a][0] >= width - 1 - BORDER_PX and quad[b][0] >= width - 1 - BORDER_PX:
            return "right"
    return None


def detect_blobs(
    photo: np.ndarray,
    white: np.ndarray | None,
    *,
    threshold: float,
    min_area: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    height, width = photo.shape[:2]
    if white is not None:
        if white.shape != photo.shape:
            raise GeometrySolveError("white photo dimensions differ from the atlas photo")
        diff = cv2.absdiff(photo, white).max(axis=2).astype(np.uint8)
        method = "white-field-difference"
    else:
        # Best-effort mode: gate on the bright panel region first so the dark
        # surround does not dominate the background estimate.
        gray = cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            raise GeometrySolveError(
                "no-white detection needs a bright panel region; give --white-photo"
            )
        panel = max(contours, key=cv2.contourArea)
        if cv2.contourArea(panel) < 0.05 * width * height:
            raise GeometrySolveError(
                "no-white detection found no plausible panel area; give --white-photo"
            )
        panel_mask = np.zeros((height, width), np.uint8)
        cv2.fillConvexPoly(
            panel_mask, cv2.boxPoints(cv2.minAreaRect(panel)).astype(np.int32), 255
        )
        # Erode past the warp-blend zone so panel-edge pixels do not become
        # phantom diff blobs.
        erode_kernel = max(3, int(round(60 * max(min(width, height) / 3000.0, 0.2))) | 1)
        panel_mask = cv2.erode(
            panel_mask, np.ones((erode_kernel, erode_kernel), np.uint8)
        )
        inside = photo[panel_mask > 0]
        background = np.median(inside, axis=0)
        diff = (
            np.abs(photo.astype(np.int16) - background.astype(np.int16))
            .max(axis=2)
            .astype(np.uint8)
        )
        diff[panel_mask == 0] = 0
        method = "panel-gated-median-background-difference"
    scale = max(min(width, height) / 3000.0, 0.2)
    # Kernels must stay below the inter-block gap (V4 compact layout: 10
    # content px gaps ~= 10-25 photo px) so adjacent blocks never merge.
    open_kernel = max(3, int(round(7 * scale)) | 1)
    close_kernel = max(3, int(round(15 * scale)) | 1)
    mask = (diff > threshold).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((open_kernel, open_kernel), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((close_kernel, close_kernel), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blobs: list[dict[str, Any]] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < min_area:
            continue
        quad = _order_quad(cv2.boxPoints(cv2.minAreaRect(contour)))
        blobs.append(
            {
                "quad": quad,
                "area": area,
                "centroid": quad.mean(axis=0),
                "truncated_edge": _truncated_edge(quad, width, height),
            }
        )
    blobs.sort(key=lambda blob: -blob["area"])
    if blobs:
        # Drop phantom blobs whose area is inconsistent with the block cluster
        # (panel-edge artifacts are much larger; specks much smaller).  Slivers
        # truncated by the frame keep a lower bound allowance.
        median_area = float(np.median([blob["area"] for blob in blobs]))
        blobs = [
            blob
            for blob in blobs
            if 0.15 * median_area <= blob["area"] <= 2.0 * median_area
        ]
    # Quad conformity: untruncated blobs whose side lengths deviate strongly
    # from the cluster median are merged/halo artifacts, not blocks (V3 diff
    # haze lesson).  They stay out of the fit but remain in the report.
    full_candidates = [blob for blob in blobs if blob["truncated_edge"] is None]
    if len(full_candidates) >= 3:
        long_sides = []
        short_sides = []
        for blob in full_candidates:
            quad = blob["quad"]
            sides = [
                float(np.linalg.norm(quad[1] - quad[0])),
                float(np.linalg.norm(quad[3] - quad[0])),
            ]
            long_sides.append(max(sides))
            short_sides.append(min(sides))
        med_long = float(np.median(long_sides))
        med_short = float(np.median(short_sides))
        for blob, long_side, short_side in zip(full_candidates, long_sides, short_sides):
            blob["nonconforming"] = bool(
                long_side > 2.2 * med_long
                or short_side > 2.2 * med_short
                or long_side < 0.45 * med_long
                or short_side < 0.45 * med_short
            )
    else:
        for blob in blobs:
            blob.setdefault("nonconforming", False)
    for blob in blobs:
        blob.setdefault("nonconforming", False)
    detail = {
        "method": method,
        "diff_threshold": threshold,
        "min_blob_area": min_area,
        "open_kernel": open_kernel,
        "close_kernel": close_kernel,
        "raw_contour_count": len(contours),
    }
    return blobs, detail


def _solve_from_points(src: np.ndarray, dst: np.ndarray) -> np.ndarray | None:
    if len(src) >= 4:
        homography, _ = cv2.findHomography(src, dst, 0)
        return homography
    if len(src) == 3:
        matrix, _ = cv2.estimateAffine2D(src, dst)
    else:
        matrix, _ = cv2.estimateAffinePartial2D(src, dst)
    if matrix is None:
        return None
    homography = np.eye(3)
    homography[:2, :] = matrix
    return homography


def _project(homography: np.ndarray, points: np.ndarray) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, homography).reshape(-1, 2)


def _best_roll(homography: np.ndarray, quad: np.ndarray, corners: np.ndarray) -> np.ndarray:
    best: tuple[float, np.ndarray] | None = None
    for shift in range(4):
        rolled = np.roll(quad, -shift, axis=0)
        error = float(np.sum((rolled - corners) ** 2))
        if best is None or error < best[0]:
            best = (error, rolled)
    assert best is not None
    return best[1]


TIE_CORNER_EPSILON = 3.0
CENTROID_PREFILTER_TOP = 256


def _rim_score(homography: np.ndarray, rim_quad: np.ndarray) -> float:
    """Mean distance of the rim quad's content-x=0 edge to the projected line."""
    return rim_error(homography, rim_quad)["rim_err"]


def _corner_refit(
    perm: tuple[str, ...],
    full_blobs: Sequence[dict[str, Any]],
    centers: Mapping[str, np.ndarray],
    corners: Mapping[str, np.ndarray],
    blob_centroids: np.ndarray,
) -> tuple[np.ndarray, float] | None:
    """Refit H on corner correspondences with per-blob roll search.

    Scoring must use corner geometry: with k<=4 blobs a homography fits
    centroids exactly for every assignment (k*2 = 8 dof), so centroid
    residuals cannot discriminate.  Corner quads overdetermine H and only
    true grid symmetries tie.  For k<=3 all 4^k roll combinations are
    enumerated (a centroid-seeded similarity can jam on a wrong roll); for
    k>=4 rolls are iterated from the centroid seed.
    """
    if len(perm) <= 3:
        best: tuple[float, np.ndarray] | None = None
        for rolls in itertools.product(range(4), repeat=len(perm)):
            src_points: list[np.ndarray] = []
            dst_points: list[np.ndarray] = []
            for blob, name, roll in zip(full_blobs, perm, rolls):
                rolled = np.roll(blob["quad"], -roll, axis=0)
                src_points.extend(corners[name])
                dst_points.extend(rolled)
            candidate, _ = cv2.findHomography(
                np.array(src_points), np.array(dst_points), 0
            )
            if candidate is None or not np.all(np.isfinite(candidate)):
                continue
            errors = []
            for blob, name, roll in zip(full_blobs, perm, rolls):
                rolled = np.roll(blob["quad"], -roll, axis=0)
                predicted = _project(candidate, corners[name])
                errors.append(np.sum((predicted - rolled) ** 2, axis=1))
            rms = float(np.sqrt(np.mean(np.concatenate(errors))))
            if not math.isfinite(rms):
                continue
            if best is None or rms < best[0]:
                best = (rms, candidate)
        return None if best is None else (best[1], best[0])
    src_centers = np.array([centers[name] for name in perm])
    seed = _solve_from_points(src_centers, blob_centroids)
    if seed is None or not np.all(np.isfinite(seed)):
        return None
    homography = seed
    rolled_quads: list[np.ndarray] = [blob["quad"] for blob in full_blobs]
    for _ in range(3):
        src_points: list[np.ndarray] = []
        dst_points: list[np.ndarray] = []
        rolled_quads = []
        for blob, name in zip(full_blobs, perm):
            rolled = _best_roll(
                homography, blob["quad"], _project(homography, corners[name])
            )
            rolled_quads.append(rolled)
            src_points.extend(corners[name])
            dst_points.extend(rolled)
        candidate, _ = cv2.findHomography(
            np.array(src_points), np.array(dst_points), 0
        )
        if candidate is None or not np.all(np.isfinite(candidate)):
            return None
        if np.allclose(candidate, homography, rtol=0, atol=1e-9):
            homography = candidate
            break
        homography = candidate
    errors = []
    for rolled, name in zip(rolled_quads, perm):
        predicted = _project(homography, corners[name])
        errors.append(np.sum((predicted - rolled) ** 2, axis=1))
    rms = float(np.sqrt(np.mean(np.concatenate(errors))))
    if not math.isfinite(rms):
        return None
    return homography, rms


def solve_assignment(
    regions: Sequence[Mapping[str, Any]],
    blobs: Sequence[dict[str, Any]],
    rim_quad: np.ndarray | None = None,
) -> dict[str, Any]:
    full = [
        (index, blob)
        for index, blob in enumerate(blobs)
        if blob["truncated_edge"] is None and not blob["nonconforming"]
    ]
    truncated = [blob for blob in blobs if blob["truncated_edge"] is not None]
    if len(full) < 2:
        raise GeometrySolveError(
            f"fewer than 2 untruncated blocks detected ({len(full)}); cannot solve"
        )
    if len(full) > len(regions):
        full = full[: len(regions)]
    k = len(full)
    blob_indices = [index for index, _ in full]
    full_blobs = [blob for _, blob in full]
    names = [region["name"] for region in regions]
    centers = {region["name"]: _rect_center(region) for region in regions}
    corners = {region["name"]: _rect_corners(region) for region in regions}
    blob_centroids = np.array([blob["centroid"] for blob in full_blobs])

    hypotheses = list(itertools.permutations(names, k))
    if k >= 5 and len(hypotheses) > CENTROID_PREFILTER_TOP:
        # Centroid residuals are overdetermined for k>=5, so wrong assignments
        # have genuinely large errors; prefilter before the corner refits.
        centroid_scores: list[tuple[float, tuple[str, ...]]] = []
        for perm in hypotheses:
            src = np.array([centers[name] for name in perm])
            candidate = _solve_from_points(src, blob_centroids)
            if candidate is None or not np.all(np.isfinite(candidate)):
                continue
            projected = _project(candidate, src)
            rms = float(
                np.sqrt(np.mean(np.sum((projected - blob_centroids) ** 2, axis=1)))
            )
            if math.isfinite(rms):
                centroid_scores.append((rms, perm))
        centroid_scores.sort(key=lambda entry: entry[0])
        hypotheses = [perm for _, perm in centroid_scores[:CENTROID_PREFILTER_TOP]]

    scored: list[dict[str, Any]] = []
    for perm in hypotheses:
        refined = _corner_refit(perm, full_blobs, centers, corners, blob_centroids)
        if refined is None:
            continue
        homography, corner_rms = refined
        scored.append({"perm": perm, "corner_rms": corner_rms, "H": homography})
    if not scored:
        raise GeometrySolveError("no assignment hypothesis produced a transform")
    scored.sort(key=lambda item: item["corner_rms"])

    # Grid symmetry note (the V3 arbitration lesson): with some blocks
    # invisible, the remaining occupancy can be rotation/mirror symmetric, so
    # wrong assignments then fit the observed quads exactly and tie.  The
    # content x=0 rim anchor breaks such ties when it clearly discriminates;
    # otherwise the tie is reported and the assignment is not reliable.
    best = scored[0]
    tied = [
        item
        for item in scored
        if item["corner_rms"] <= best["corner_rms"] + TIE_CORNER_EPSILON
    ]
    tie_broken_by = None
    tie_rim_errors: list[dict[str, Any]] = []
    if len(tied) > 1 and rim_quad is not None:
        rim_scored = []
        for item in tied:
            rim_err = _rim_score(item["H"], rim_quad)
            rim_scored.append((rim_err, item))
            tie_rim_errors.append(
                {
                    "assignment": {
                        f"blob_{blob_indices[pos]}": name
                        for pos, name in enumerate(item["perm"])
                    },
                    "corner_rms": round(item["corner_rms"], 3),
                    "rim_err": round(rim_err, 3),
                }
            )
        rim_scored.sort(key=lambda entry: entry[0])
        # V3 real-data lesson: 22 vs 21 px is NOT a decision; the rim decides
        # only with a clear margin, otherwise report, do not guess.
        if len(rim_scored) == 1 or rim_scored[0][0] * 2.0 <= rim_scored[1][0]:
            best = rim_scored[0][1]
            tie_broken_by = "rim_x0_anchor"

    margin = None
    for runner in scored:
        if runner["perm"] != best["perm"]:
            margin = runner["corner_rms"] - best["corner_rms"]
            break

    homography = best["H"]
    mapping = dict(zip(blob_indices, best["perm"]))
    per_block: dict[str, float] = {}
    for blob, name in zip(full_blobs, best["perm"]):
        predicted = _project(homography, corners[name])
        per_block[name] = round(
            float(np.sqrt(np.mean(np.sum((predicted - blob["quad"]) ** 2, axis=1)))),
            3,
        )
    reliable = k >= 3 and (len(tied) == 1 or tie_broken_by is not None)

    truncated_matches: dict[str, dict[str, Any]] = {}
    assigned = set(best["perm"])
    opposite = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}
    edge_points = {"top": (0, 1), "right": (1, 2), "bottom": (2, 3), "left": (3, 0)}
    for blob in truncated:
        edge = opposite[blob["truncated_edge"]]
        a, b = edge_points[edge]
        interior_mid = (blob["quad"][a] + blob["quad"][b]) / 2.0
        best_match: tuple[float, str] | None = None
        for name in names:
            if name in assigned:
                continue
            projected = _project(homography, corners[name])
            mid = (projected[a] + projected[b]) / 2.0
            distance = float(np.linalg.norm(mid - interior_mid))
            if best_match is None or distance < best_match[0]:
                best_match = (distance, name)
        if best_match is not None and best_match[0] <= TRUNCATED_MATCH_MAX_DIST:
            truncated_matches[best_match[1]] = {
                "truncated_edge": blob["truncated_edge"],
                "interior_edge_midpoint_error": round(best_match[0], 2),
            }
            assigned.add(best_match[1])

    return {
        "homography": homography,
        "mapping": mapping,
        "assigned_names": sorted(assigned),
        "full_block_names": list(best["perm"]),
        "truncated_matches": truncated_matches,
        "per_block_reprojection_rms": per_block,
        "ranking_top": [
            {
                "assignment": {
                    f"blob_{blob_indices[pos]}": name
                    for pos, name in enumerate(item["perm"])
                },
                "corner_rms": round(item["corner_rms"], 3),
            }
            for item in scored[:5]
        ],
        "runner_up_margin": None if margin is None else round(margin, 3),
        "corner_score_tie_count": len(tied),
        "tie_broken_by": tie_broken_by,
        "tie_rim_errors": tie_rim_errors,
        "reliable": reliable,
        "hypothesis_count": len(scored),
    }


def detect_rim(rim_photo: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(rim_photo, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (9, 9), 0)
    # Two-stage Otsu: the first split can swallow a mid-bright bezel; the
    # second stage re-splits the bright class (V3 OTP-white lesson).
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bright_pixels = blurred[binary > 0]
    if bright_pixels.size > 100:
        stage2, _ = cv2.threshold(
            bright_pixels, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        refined = (blurred > stage2).astype(np.uint8) * 255
        refined = cv2.morphologyEx(
            refined, cv2.MORPH_OPEN, np.ones((15, 15), np.uint8)
        )
        contours2, _ = cv2.findContours(
            refined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if contours2 and cv2.contourArea(max(contours2, key=cv2.contourArea)) >= (
            0.01 * gray.shape[0] * gray.shape[1]
        ):
            binary = refined
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise GeometrySolveError("rim photo: no bright region detected")
    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < 0.01 * gray.shape[0] * gray.shape[1]:
        raise GeometrySolveError("rim photo: bright active area implausibly small")
    quad = _order_quad(cv2.boxPoints(cv2.minAreaRect(contour)))
    height, width = gray.shape
    coverage = float(
        cv2.contourArea(cv2.boxPoints(cv2.minAreaRect(contour)).astype(np.float32))
    ) / float(width * height)
    if coverage > 0.98:
        raise GeometrySolveError(
            "rim photo: bright region covers the whole frame; no rim edge identifiable"
        )
    return quad


def rim_error(homography: np.ndarray, rim_quad: np.ndarray) -> dict[str, Any]:
    """Distance of the projected content x=0 line to the rim's left vertical edge.

    Rig convention (same as the V3 arbitration): the panel active-area left
    edge in the photo is content x=0.  The leftmost of the rim quad's two
    vertical edges is the anchor; a rotated hypothesis projects content x=0 to
    the opposite side of the panel and scores ~panel-width, which is how the
    rim breaks assignment ties.
    """
    line_points = _project(homography, np.array([(0.0, 0.0), (0.0, SCREEN_HEIGHT)]))
    p0, p1 = line_points
    direction = p1 - p0
    normal = np.array([-direction[1], direction[0]])
    normal /= np.linalg.norm(normal)

    def distance(point: np.ndarray) -> float:
        return abs(float(np.dot(point - p0, normal)))

    vertical_edges = [(3, 0), (1, 2)]  # left, right in ordered quad
    best_edge = min(
        vertical_edges,
        key=lambda edge: (rim_quad[edge[0]][0] + rim_quad[edge[1]][0]) / 2.0,
    )
    a, b = rim_quad[best_edge[0]], rim_quad[best_edge[1]]
    samples = [a + (b - a) * index / (RIM_SAMPLE_POINTS - 1) for index in range(RIM_SAMPLE_POINTS)]
    errors = [distance(sample) for sample in samples]
    return {
        "anchor": "content x=0 line to photo-left vertical rim edge (rig convention)",
        "rim_quad": np.round(rim_quad, 2).tolist(),
        "selected_edge": [int(best_edge[0]), int(best_edge[1])],
        "sample_count": RIM_SAMPLE_POINTS,
        "rim_err": round(float(np.mean(errors)), 2),
        "rim_err_max": round(float(np.max(errors)), 2),
    }


def _encode_jpeg(image: np.ndarray, label: str) -> bytes:
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise GeometrySolveError(f"cannot encode {label}")
    return encoded.tobytes()


def _encode_png(image: np.ndarray, label: str) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise GeometrySolveError(f"cannot encode {label}")
    return encoded.tobytes()


def _overlay(
    photo: np.ndarray,
    blobs: Sequence[dict[str, Any]],
    regions: Sequence[Mapping[str, Any]],
    homography: np.ndarray,
    rim_quad: np.ndarray | None,
) -> bytes:
    vis = photo.copy()
    for blob in blobs:
        quad = blob["quad"].astype(np.int32)
        color = (0, 255, 0) if blob["truncated_edge"] is None else (0, 165, 255)
        cv2.polylines(vis, [quad], True, color, 4)
    panel = _project(
        homography,
        np.array([(0, 0), (SCREEN_WIDTH, 0), (SCREEN_WIDTH, SCREEN_HEIGHT), (0, SCREEN_HEIGHT)]),
    ).astype(np.int32)
    cv2.polylines(vis, [panel], True, (255, 0, 0), 3)
    for region in regions:
        quad = _project(homography, _rect_corners(region)).astype(np.int32)
        cv2.polylines(vis, [quad], True, (0, 0, 255), 2)
        center = quad.mean(axis=0).astype(int)
        cv2.putText(
            vis, region["name"], (center[0] - 60, center[1]),
            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3,
        )
    if rim_quad is not None:
        cv2.polylines(vis, [rim_quad.astype(np.int32)], True, (0, 255, 255), 3)
    return _encode_jpeg(vis, "overlay")


def solve(
    *,
    photo_file: str | Path,
    roi_list_file: str | Path,
    output_dir: str | Path,
    white_photo_file: str | Path | None = None,
    rim_photo_file: str | Path | None = None,
    diff_threshold: float = DEFAULT_DIFF_THRESHOLD,
    min_blob_area: float = DEFAULT_MIN_BLOB_AREA,
    min_delta_l: float = 2.0,
    min_delta_e: float = 3.0,
) -> dict[str, Any]:
    output = Path(output_dir)
    if output.exists():
        raise GeometrySolveError(f"output directory already exists: {output}")

    regions, roi_payload, revision = _load_roi_list(Path(roi_list_file))
    photo_path = Path(photo_file)
    photo_payload, photo = _read_image(photo_path, label="photo")
    white = None
    white_payload = None
    white_path = None
    if white_photo_file is not None:
        white_path = Path(white_photo_file)
        white_payload, white = _read_image(white_path, label="white photo")
    rim = None
    rim_payload = None
    rim_path = None
    if rim_photo_file is not None:
        rim_path = Path(rim_photo_file)
        rim_payload, rim_image = _read_image(rim_path, label="rim photo")
        rim = detect_rim(rim_image)

    blobs, detection_detail = detect_blobs(
        photo, white, threshold=diff_threshold, min_area=min_blob_area
    )
    assignment = solve_assignment(regions, blobs, rim_quad=rim)
    homography = assignment["homography"]

    detected_names = assignment["assigned_names"]
    per_block: list[dict[str, Any]] = []
    for region in regions:
        name = region["name"]
        projected = _project(homography, _rect_corners(region))
        height, width = photo.shape[:2]
        per_block.append(
            {
                "name": name,
                "code": region["code"],
                "content_rect": [region["x"], region["y"], region["w"], region["h"]],
                "detected": name in detected_names,
                "detection": (
                    "full"
                    if name in assignment["full_block_names"]
                    else ("truncated" if name in assignment["truncated_matches"] else None)
                ),
                "reprojection_rms": assignment["per_block_reprojection_rms"].get(name),
                "photo_quad_pred": np.round(projected, 2).tolist(),
                "fully_in_frame_pred": bool(
                    projected[:, 0].min() >= 0
                    and projected[:, 1].min() >= 0
                    and projected[:, 0].max() <= width
                    and projected[:, 1].max() <= height
                ),
            }
        )

    inverse = np.linalg.inv(homography)
    warped = cv2.warpPerspective(
        photo, inverse, (SCREEN_WIDTH, SCREEN_HEIGHT), flags=cv2.INTER_LINEAR
    )
    warped_white = None
    if white is not None:
        warped_white = cv2.warpPerspective(
            white, inverse, (SCREEN_WIDTH, SCREEN_HEIGHT), flags=cv2.INTER_LINEAR
        )

    output.mkdir(parents=True, exist_ok=False)
    warped_path = output / "warped.png"
    _write_new(warped_path, _encode_png(warped, "warped content plane"))
    white_warped_path = None
    if warped_white is not None:
        white_warped_path = output / "white-warped.png"
        _write_new(white_warped_path, _encode_png(warped_white, "warped white field"))

    lab_result = roi_lab.measure(
        image=warped_path,
        layout_file=Path(roi_list_file),
        report_file=output / "lab-report.json",
        annotated_file=output / "lab-annotated.png",
        white_reference_image=white_warped_path,
        min_delta_l=min_delta_l,
        min_delta_e=min_delta_e,
    )

    overlay_payload = _overlay(photo, blobs, regions, homography, rim)
    _write_new(output / "overlay.jpg", overlay_payload)

    rim_report = None
    if rim is not None:
        rim_report = rim_error(homography, rim)
        rim_report["photo"] = _file_record(rim_path, rim_payload)  # type: ignore[arg-type]

    report_unsigned: dict[str, Any] = {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "offline_only": True,
        "inputs": {
            "photo": _file_record(photo_path, photo_payload),
            "white_photo": None
            if white_path is None
            else _file_record(white_path, white_payload),  # type: ignore[arg-type]
            "rim_photo": None
            if rim_path is None
            else _file_record(rim_path, rim_payload),  # type: ignore[arg-type]
            "roi_list": _file_record(Path(roi_list_file), roi_payload),
        },
        "roi_list": {
            "layout_revision": revision,
            "region_count": len(regions),
            "codes": [region["code"] for region in regions],
        },
        "detection": {
            **detection_detail,
            "blob_count": len(blobs),
            "blobs": [
                {
                    "index": index,
                    "quad": np.round(blob["quad"], 2).tolist(),
                    "area": round(blob["area"], 1),
                    "centroid": np.round(blob["centroid"], 2).tolist(),
                    "truncated_edge": blob["truncated_edge"],
                    "nonconforming": blob["nonconforming"],
                }
                for index, blob in enumerate(blobs)
            ],
        },
        "assignment": {
            "mapping": {f"blob_{index}": name for index, name in assignment["mapping"].items()},
            "full_blocks_used": len(assignment["full_block_names"]),
            "truncated_matches": assignment["truncated_matches"],
            "ranking_top": assignment["ranking_top"],
            "runner_up_margin": assignment["runner_up_margin"],
            "corner_score_tie_count": assignment["corner_score_tie_count"],
            "tie_broken_by": assignment["tie_broken_by"],
            "tie_rim_errors": assignment["tie_rim_errors"],
            "reliable": assignment["reliable"],
            "hypothesis_count": assignment["hypothesis_count"],
            "invisible_blocks_are_simply_missing": True,
        },
        "homography_content_to_photo": np.round(homography, 8).tolist(),
        "blocks": per_block,
        "detected": detected_names,
        "missing": [region["name"] for region in regions if region["name"] not in detected_names],
        "rim": rim_report,
        "lab": lab_result,
        "outputs": {
            "geometry": "geometry.json",
            "overlay": "overlay.jpg",
            "warped": "warped.png",
            "lab_report": "lab-report.json",
            "lab_annotated": "lab-annotated.png",
        },
        "evidence_boundaries": {
            "camera_relative_only": True,
            "no_panel_corners_required": True,
            "device_io_performed": False,
        },
    }
    report = roi_lab.seal_report(report_unsigned)
    _write_new(output / "geometry.json", _pretty(report))
    return {
        "output_dir": str(output.resolve()),
        "geometry_file": str((output / "geometry.json").resolve()),
        "geometry_canonical_sha256": report["integrity"]["sha256"],
        "assignment": assignment["mapping"],
        "detected": detected_names,
        "missing": report_unsigned["missing"],
        "rim_err": None if rim_report is None else rim_report["rim_err"],
        "lab_report": lab_result["report_file"],
        "device_io_performed": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--photo", type=Path, required=True, help="atlas photo")
    parser.add_argument("--roi-list", type=Path, required=True, help="roi-list JSON (content rects)")
    parser.add_argument("--white-photo", type=Path, help="batch-internal white-field photo (diff detection + Lab white reference)")
    parser.add_argument("--rim-photo", type=Path, help="white-field photo for the content x=0 rim anchor")
    parser.add_argument("--output-dir", type=Path, required=True, help="created exclusively")
    parser.add_argument("--threshold", type=float, default=DEFAULT_DIFF_THRESHOLD, help="block diff threshold (default 15)")
    parser.add_argument("--min-blob-area", type=float, default=DEFAULT_MIN_BLOB_AREA, help="minimum blob area in photo px (default 500)")
    parser.add_argument("--min-delta-l", type=float, default=2.0, help="Lab resolvable_vs_white |dL| threshold")
    parser.add_argument("--min-delta-e", type=float, default=3.0, help="Lab resolvable_vs_white dE76 threshold")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = solve(
            photo_file=args.photo,
            roi_list_file=args.roi_list,
            output_dir=args.output_dir,
            white_photo_file=args.white_photo,
            rim_photo_file=args.rim_photo,
            diff_threshold=args.threshold,
            min_blob_area=args.min_blob_area,
            min_delta_l=args.min_delta_l,
            min_delta_e=args.min_delta_e,
        )
    except GeometrySolveError as error:
        print(f"block geometry solve error: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
