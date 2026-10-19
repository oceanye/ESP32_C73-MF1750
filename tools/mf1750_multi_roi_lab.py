#!/usr/bin/env python3
"""Measure camera-relative Lab of multiple layout-defined ROIs from one photo.

Route-A experiment support: a white-background frame carries 4-8 large colour
blocks, one refresh, one photograph; this tool measures every block at once.

Input is either an already-warped 1024x600 panel-plane image (--image) or a
raw camera photo (--photo) rectified with the fixed batch quad (default
relative corners TL/TR/BR/BL, overridable with --corners).  The layout JSON
lists regions in 1024x600 screen coordinates; each region gets a 10% inset
margin on every side before statistics are taken.

Lab convention (kept identical to the existing batches):
- sRGB8 -> CIE L*a*b* (D65/2deg) vectorized exactly as
  tools/mf1750_lh1_rebound_v2_middle_photo_analyzer.py::srgb_to_lab_batch,
  which is cross-checked there against
  host/color_pipeline/color.py::srgb8_to_lab.
- Per-region statistics follow the batch *-lab.json shape (e.g.
  .test-output/hardware/WF_WMASK_0E_R0R3_20261019_V1/03-0e-r0r3-lab.json):
  per-pixel Lab mean reported as L/a/b plus std_L (population std of L*),
  rounded to 2 decimals.  The multi-ROI mean/std form mirrors
  tools/mf1750_ec5_dither_atlas_photo_analyzer.py::_roi_measurements.
- Illumination estimate follows the batch illumination-gate.json practice
  (e.g. .test-output/hardware/DITHER_ATLAS_DAYLIGHT_20261011_V1): grayscale
  p95 of the white-background screen area, optionally divided by a reference
  p95 (--reference-p95) with the 0.85/1.2 gate.

The report is self-sealed with the tools/mf1750_wmask_atlas.py integrity
convention: sha256 of the canonical JSON without the integrity member.
--verify re-checks a written report.  Output files are created exclusively
(O_EXCL); nothing is overwritten.  No hardware, serial, relay, network,
camera, or flashing access is performed.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import stat
from typing import Any, Mapping, Sequence

import cv2
import numpy as np


SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 600
INSET_FRACTION = 0.10
DEFAULT_RELATIVE_QUAD = (
    (0.3960, 0.1707),
    (0.8648, 0.1577),
    (0.8890, 0.5557),
    (0.3327, 0.5147),
)
HIGH_CLIP_THRESHOLD = 250
LOW_CLIP_THRESHOLD = 3
MIN_WHITE_BACKGROUND_PIXELS = 1000
GATE_LOW = 0.85
GATE_HIGH = 1.2
REPORT_KIND = "mf1750-multi-roi-camera-relative-lab"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"

LAB_CONVENTION = {
    "space": "CIE L*a*b* D65/2deg decoded from sRGB8 (camera-relative)",
    "srgb_to_lab_source": (
        "tools/mf1750_lh1_rebound_v2_middle_photo_analyzer.py::srgb_to_lab_batch"
        " (cross-checked against host/color_pipeline/color.py::srgb8_to_lab)"
    ),
    "statistics_source": (
        "batch *-lab.json shape (L/a/b/std_L, 2 decimals) as in"
        " .test-output/hardware/WF_WMASK_0E_R0R3_20261019_V1/03-0e-r0r3-lab.json;"
        " multi-ROI mean/std form as in"
        " tools/mf1750_ec5_dither_atlas_photo_analyzer.py::_roi_measurements"
    ),
    "illumination_source": (
        "batch illumination-gate.json white-region p95 ratio practice as in"
        " .test-output/hardware/DITHER_ATLAS_DAYLIGHT_20261011_V1/illumination-gate.json"
    ),
    "calibrated": False,
    "camera_is_not_a_colorimeter": True,
}


class MultiRoiLabError(ValueError):
    """Raised for invalid images, layouts, corners, or output boundaries."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _pretty(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(payload)


def seal_report(unsigned: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(unsigned)
    sealed["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _sha256(_canonical(unsigned)),
    }
    return sealed


def verify_report(path: str | Path) -> dict[str, Any]:
    report_path = Path(path)
    try:
        document = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MultiRoiLabError(f"cannot read report {report_path}: {error}") from error
    if not isinstance(document, dict):
        raise MultiRoiLabError("report must contain a JSON object")
    integrity = document.get("integrity")
    if not isinstance(integrity, dict):
        raise MultiRoiLabError("report has no integrity member")
    if integrity.get("algorithm") != INTEGRITY_ALGORITHM:
        raise MultiRoiLabError("report integrity algorithm differs")
    declared = integrity.get("sha256")
    unsigned = dict(document)
    unsigned.pop("integrity")
    actual = _sha256(_canonical(unsigned))
    if declared != actual:
        raise MultiRoiLabError(
            f"report integrity mismatch: declared {declared}, recomputed {actual}"
        )
    return {"file": str(report_path.resolve()), "integrity_sha256": actual}


def srgb8_to_lab_batch(rgb: np.ndarray) -> np.ndarray:
    """Vectorized sRGB8 -> CIE L*a*b* (D65/2deg).

    Replica of tools/mf1750_lh1_rebound_v2_middle_photo_analyzer.py
    ::srgb_to_lab_batch, cross-checked against the host pipeline
    host/color_pipeline/color.py::srgb8_to_lab.
    """
    f = rgb.astype(np.float64) / 255.0
    lin = np.where(f <= 0.04045, f / 12.92, ((f + 0.055) / 1.055) ** 2.4)
    m = np.array(
        [
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041],
        ]
    )
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    e = 216 / 24389
    k = 24389 / 27
    fxyz = np.where(xyz > e, np.cbrt(xyz), (k * xyz + 16) / 116)
    return np.stack(
        [
            116 * fxyz[:, 1] - 16,
            500 * (fxyz[:, 0] - fxyz[:, 1]),
            200 * (fxyz[:, 1] - fxyz[:, 2]),
        ],
        axis=1,
    )


def _read_image(path: Path, *, label: str) -> tuple[bytes, np.ndarray]:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise MultiRoiLabError(f"{label} must be a regular non-symlink")
        payload = path.read_bytes()
    except OSError as error:
        raise MultiRoiLabError(f"{label} cannot be read: {error}") from error
    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise MultiRoiLabError(f"{label} is not a supported three-channel image")
    if image.shape[0] < 100 or image.shape[1] < 100:
        raise MultiRoiLabError(f"{label} is too small")
    return payload, image


def _load_layout(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    try:
        payload = path.read_bytes()
        document = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MultiRoiLabError(f"layout cannot be read: {error}") from error
    if isinstance(document, list):
        raw_regions = document
        screen = None
    elif isinstance(document, dict):
        screen = document.get("screen")
        raw_regions = document.get("regions", document.get("rois"))
    else:
        raise MultiRoiLabError("layout root must be an object or an array")
    if screen is not None:
        if (
            not isinstance(screen, Mapping)
            or screen.get("width") != SCREEN_WIDTH
            or screen.get("height") != SCREEN_HEIGHT
        ):
            raise MultiRoiLabError(
                f"layout screen must be {SCREEN_WIDTH}x{SCREEN_HEIGHT} when declared"
            )
    if not isinstance(raw_regions, list) or not raw_regions:
        raise MultiRoiLabError("layout must contain a non-empty regions array")
    if len(raw_regions) > 64:
        raise MultiRoiLabError("layout contains more than 64 regions")
    regions: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, raw in enumerate(raw_regions):
        label = f"layout region {index}"
        if not isinstance(raw, Mapping):
            raise MultiRoiLabError(f"{label} must be an object")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise MultiRoiLabError(f"{label} requires a non-empty name")
        if name in names:
            raise MultiRoiLabError(f"duplicate region name {name!r}")
        names.add(name)
        code = raw.get("code")
        if code is not None and (
            isinstance(code, bool) or not isinstance(code, (int, str))
        ):
            raise MultiRoiLabError(f"region {name!r} code must be int, str, or null")
        numbers: dict[str, float] = {}
        for key, aliases in (
            ("x", ("x",)),
            ("y", ("y",)),
            ("w", ("w", "width")),
            ("h", ("h", "height")),
        ):
            value = next((raw[a] for a in aliases if a in raw), None)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise MultiRoiLabError(f"region {name!r} requires numeric {key}")
            if not math.isfinite(float(value)):
                raise MultiRoiLabError(f"region {name!r} {key} is not finite")
            numbers[key] = float(value)
        x, y, w, h = numbers["x"], numbers["y"], numbers["w"], numbers["h"]
        if w < 10 or h < 10:
            raise MultiRoiLabError(f"region {name!r} is smaller than 10x10 px")
        if x < 0 or y < 0 or x + w > SCREEN_WIDTH or y + h > SCREEN_HEIGHT:
            raise MultiRoiLabError(
                f"region {name!r} escapes the {SCREEN_WIDTH}x{SCREEN_HEIGHT} screen"
            )
        regions.append({"name": name, "code": code, "x": x, "y": y, "w": w, "h": h})
    return regions, payload


def _resolve_corners(
    text: str | None, width: int, height: int
) -> tuple[np.ndarray, list[list[float]], bool]:
    """Resolve TL TR BR BL corners to absolute source pixels.

    Values in [0, 1] (all four points) are treated as relative to the photo
    dimensions; otherwise absolute pixels.  Without --corners the fixed batch
    quad DEFAULT_RELATIVE_QUAD is used.
    """
    if text is None:
        points = [list(pair) for pair in DEFAULT_RELATIVE_QUAD]
        relative = True
        default_used = True
    else:
        parts = text.replace(";", " ").split()
        if len(parts) != 4:
            raise MultiRoiLabError("--corners requires four x,y points: TL TR BR BL")
        points = []
        try:
            for part in parts:
                x_text, y_text = part.split(",", maxsplit=1)
                point = [float(x_text), float(y_text)]
                if not all(math.isfinite(value) for value in point):
                    raise ValueError("non-finite corner")
                points.append(point)
        except ValueError as error:
            raise MultiRoiLabError("--corners contains an invalid x,y point") from error
        relative = all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in points)
        default_used = False
    if relative:
        absolute = [[x * width, y * height] for x, y in points]
    else:
        absolute = points
    result = np.asarray(absolute, dtype=np.float32)
    if (
        np.any(result[:, 0] < 0)
        or np.any(result[:, 0] >= width)
        or np.any(result[:, 1] < 0)
        or np.any(result[:, 1] >= height)
    ):
        raise MultiRoiLabError("corners escape the source photo")
    contour = result.reshape((-1, 1, 2))
    if not cv2.isContourConvex(contour) or abs(cv2.contourArea(contour)) < 1000:
        raise MultiRoiLabError("corners are not a sufficiently large convex quad")
    return result, points, default_used


def warp_to_screen(source: np.ndarray, corners: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Same quad warp as host/static_photo/history_analysis.py:166-169."""
    target = np.asarray(
        [
            [0, 0],
            [SCREEN_WIDTH - 1, 0],
            [SCREEN_WIDTH - 1, SCREEN_HEIGHT - 1],
            [0, SCREEN_HEIGHT - 1],
        ],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(corners, target)
    warped = cv2.warpPerspective(
        source, transform, (SCREEN_WIDTH, SCREEN_HEIGHT), flags=cv2.INTER_LINEAR
    )
    return warped, transform


def _inset_rectangle(region: Mapping[str, Any]) -> tuple[int, int, int, int]:
    margin_x = region["w"] * INSET_FRACTION
    margin_y = region["h"] * INSET_FRACTION
    x0 = int(math.floor(region["x"] + margin_x))
    y0 = int(math.floor(region["y"] + margin_y))
    x1 = int(math.ceil(region["x"] + region["w"] - margin_x))
    y1 = int(math.ceil(region["y"] + region["h"] - margin_y))
    if not (0 <= x0 < x1 <= SCREEN_WIDTH and 0 <= y0 < y1 <= SCREEN_HEIGHT):
        raise MultiRoiLabError(f"region {region['name']!r} inset rectangle collapsed")
    return x0, y0, x1, y1


def _measure_regions(
    warped_bgr: np.ndarray, regions: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    measurements: list[dict[str, Any]] = []
    for region in regions:
        x0, y0, x1, y1 = _inset_rectangle(region)
        pixels_bgr = warped_bgr[y0:y1, x0:x1]
        pixels_rgb = pixels_bgr.reshape(-1, 3)[:, ::-1]
        labs = srgb8_to_lab_batch(pixels_rgb)
        mean_lab = labs.mean(axis=0)
        std_l = float(labs[:, 0].std())
        median_rgb = np.median(pixels_rgb, axis=0)
        measurements.append(
            {
                "name": region["name"],
                "code": region["code"],
                "rectangle": {
                    "x": region["x"],
                    "y": region["y"],
                    "width": region["w"],
                    "height": region["h"],
                },
                "analysis_rectangle": {
                    "x": x0,
                    "y": y0,
                    "x1_exclusive": x1,
                    "y1_exclusive": y1,
                },
                "inset_fraction": INSET_FRACTION,
                "pixel_count": int((x1 - x0) * (y1 - y0)),
                "L": round(float(mean_lab[0]), 2),
                "a": round(float(mean_lab[1]), 2),
                "b": round(float(mean_lab[2]), 2),
                "std_L": round(std_l, 2),
                "median_rgb8": [round(float(value), 2) for value in median_rgb],
                "high_clip_fraction": round(
                    float(np.mean(np.any(pixels_rgb >= HIGH_CLIP_THRESHOLD, axis=1))), 6
                ),
                "low_clip_fraction": round(
                    float(np.mean(np.any(pixels_rgb <= LOW_CLIP_THRESHOLD, axis=1))), 6
                ),
            }
        )
    return measurements


def _illumination(
    warped_bgr: np.ndarray,
    regions: Sequence[Mapping[str, Any]],
    reference_p95: float | None,
) -> dict[str, Any]:
    """White-background grayscale p95 vs reference (batch illumination-gate)."""
    gray = cv2.cvtColor(warped_bgr, cv2.COLOR_BGR2GRAY)
    covered = np.zeros(gray.shape, dtype=bool)
    for region in regions:
        x0 = int(math.floor(region["x"]))
        y0 = int(math.floor(region["y"]))
        x1 = int(math.ceil(region["x"] + region["w"]))
        y1 = int(math.ceil(region["y"] + region["h"]))
        covered[y0:y1, x0:x1] = True
    white = gray[~covered]
    if white.size < MIN_WHITE_BACKGROUND_PIXELS:
        raise MultiRoiLabError(
            f"white background area too small for p95: {white.size} px"
        )
    p95 = float(np.percentile(white, 95))
    ratio = None if reference_p95 is None else round(p95 / reference_p95, 4)
    return {
        "definition": (
            "grayscale p95 of screen pixels outside all region rectangles"
            " (white background), optionally relative to --reference-p95"
        ),
        "white_background_pixel_count": int(white.size),
        "grayscale_p95": round(p95, 2),
        "reference_p95": reference_p95,
        "ratio": ratio,
        "gate_low": GATE_LOW,
        "gate_high": GATE_HIGH,
        "gate_passed": None if ratio is None else GATE_LOW <= ratio <= GATE_HIGH,
    }


def _annotate(
    warped_bgr: np.ndarray, measurements: Sequence[Mapping[str, Any]]
) -> bytes:
    annotated = warped_bgr.copy()
    for measurement in measurements:
        rectangle = measurement["rectangle"]
        outer = (
            int(round(rectangle["x"])),
            int(round(rectangle["y"])),
            int(round(rectangle["x"] + rectangle["width"])),
            int(round(rectangle["y"] + rectangle["height"])),
        )
        inset = measurement["analysis_rectangle"]
        cv2.rectangle(annotated, (outer[0], outer[1]), (outer[2] - 1, outer[3] - 1), (0, 0, 0), 2)
        cv2.rectangle(
            annotated,
            (inset["x"], inset["y"]),
            (inset["x1_exclusive"] - 1, inset["y1_exclusive"] - 1),
            (255, 255, 255),
            1,
        )
        code = measurement["code"]
        label = f"{measurement['name']}"
        if code is not None:
            label += f" c{code}"
        cv2.putText(
            annotated, label, (outer[0] + 4, outer[1] + 18),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2, cv2.LINE_AA,
        )
        cv2.putText(
            annotated, label, (outer[0] + 4, outer[1] + 18),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA,
        )
        values = f"L{measurement['L']:.2f} a{measurement['a']:.2f} b{measurement['b']:.2f}"
        cv2.putText(
            annotated, values, (outer[0] + 4, outer[1] + 36),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2, cv2.LINE_AA,
        )
        cv2.putText(
            annotated, values, (outer[0] + 4, outer[1] + 36),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA,
        )
    ok, encoded = cv2.imencode(".png", annotated)
    if not ok:
        raise MultiRoiLabError("cannot encode annotated overlay")
    return encoded.tobytes()


def _file_record(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "name": path.name,
        "bytes": len(payload),
        "sha256": _sha256(payload),
    }


def measure(
    *,
    layout_file: str | Path,
    report_file: str | Path,
    image: str | Path | None = None,
    photo: str | Path | None = None,
    corners_text: str | None = None,
    reference_p95: float | None = None,
    annotated_file: str | Path | None = None,
    warped_out_file: str | Path | None = None,
) -> dict[str, Any]:
    if (image is None) == (photo is None):
        raise MultiRoiLabError("exactly one of image (warped) or photo (raw) is required")
    if reference_p95 is not None and reference_p95 <= 0:
        raise MultiRoiLabError("--reference-p95 must be positive")

    regions, layout_payload = _load_layout(Path(layout_file))
    registration: dict[str, Any]
    if image is not None:
        image_path = Path(image)
        image_payload, decoded = _read_image(image_path, label="warped image")
        if decoded.shape[1] != SCREEN_WIDTH or decoded.shape[0] != SCREEN_HEIGHT:
            raise MultiRoiLabError(
                f"warped image must be exactly {SCREEN_WIDTH}x{SCREEN_HEIGHT}; "
                f"got {decoded.shape[1]}x{decoded.shape[0]} (use --photo for raw photos)"
            )
        warped = decoded
        registration = {
            "mode": "warped-image",
            "screen_plane_identity": True,
            "warp_performed": False,
        }
    else:
        image_path = Path(photo)  # type: ignore[arg-type]
        image_payload, decoded = _read_image(image_path, label="photo")
        source_height, source_width = decoded.shape[:2]
        corners, requested_points, default_used = _resolve_corners(
            corners_text, source_width, source_height
        )
        warped, transform = warp_to_screen(decoded, corners)
        registration = {
            "mode": "raw-photo-quad-warp",
            "warp_performed": True,
            "corner_order": "TL_TR_BR_BL",
            "corners_relative_tl_tr_br_bl": requested_points,
            "corners_source_px_tl_tr_br_bl": corners.astype(float).tolist(),
            "default_batch_quad_used": default_used,
            "warp_algorithm": "cv2.getPerspectiveTransform + cv2.warpPerspective INTER_LINEAR",
            "warp_source": "host/static_photo/history_analysis.py lines 162-169",
            "perspective_transform": transform.astype(float).tolist(),
            "screen_size": [SCREEN_WIDTH, SCREEN_HEIGHT],
        }

    measurements = _measure_regions(warped, regions)
    illumination = _illumination(warped, regions, reference_p95)

    derived_payloads: dict[str, tuple[Path, bytes]] = {}
    if annotated_file is not None:
        derived_payloads["annotated"] = (
            Path(annotated_file),
            _annotate(warped, measurements),
        )
    if warped_out_file is not None:
        ok, encoded = cv2.imencode(".png", warped)
        if not ok:
            raise MultiRoiLabError("cannot encode warped panel image")
        derived_payloads["warped"] = (Path(warped_out_file), encoded.tobytes())
    derived_records = {
        key: _file_record(path, payload)
        for key, (path, payload) in derived_payloads.items()
    }

    report_unsigned: dict[str, Any] = {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "offline_only": True,
        "source": {
            "image": _file_record(image_path, image_payload),
            "layout": _file_record(Path(layout_file), layout_payload),
        },
        "registration": registration,
        "screen": {"width": SCREEN_WIDTH, "height": SCREEN_HEIGHT},
        "inset_fraction_per_side": INSET_FRACTION,
        "lab_convention": LAB_CONVENTION,
        "regions": measurements,
        "illumination": illumination,
        "derived_images": derived_records,
        "evidence_boundaries": {
            "camera_relative_only": True,
            "camera_is_not_a_colorimeter": True,
            "absolute_colour_qualification": False,
            "device_io_performed": False,
        },
    }
    report = seal_report(report_unsigned)
    report_payload = _pretty(report)
    _write_new(Path(report_file), report_payload)
    for path, payload in derived_payloads.values():
        _write_new(path, payload)
    return {
        "report_file": str(Path(report_file).resolve()),
        "report_canonical_sha256": report["integrity"]["sha256"],
        "region_count": len(measurements),
        "regions": [
            {
                "name": item["name"],
                "code": item["code"],
                "L": item["L"],
                "a": item["a"],
                "b": item["b"],
                "std_L": item["std_L"],
            }
            for item in measurements
        ],
        "illumination": illumination,
        "device_io_performed": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--image", type=Path, help="already-warped 1024x600 panel image")
    parser.add_argument("--photo", type=Path, help="raw camera photo (quad warp applied)")
    parser.add_argument(
        "--corners",
        help='panel corners "TLx,TLy TRx,TRy BRx,BRy BLx,BLy"; relative (0..1) or '
        "source pixels; default is the fixed batch quad",
    )
    parser.add_argument("--layout", type=Path, help="layout JSON with screen-coordinate regions")
    parser.add_argument("--report", type=Path, help="output report JSON (created exclusively)")
    parser.add_argument("--annotated", type=Path, help="optional annotated overlay PNG")
    parser.add_argument("--warped-out", type=Path, help="optional warped panel PNG (photo mode)")
    parser.add_argument("--reference-p95", type=float, help="reference white p95 for the illumination ratio")
    parser.add_argument("--verify", type=Path, help="re-check an existing report's integrity and exit")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.verify is not None:
            print(json.dumps(verify_report(args.verify), ensure_ascii=False, sort_keys=True))
            return 0
        if args.layout is None or args.report is None:
            raise MultiRoiLabError("--layout and --report are required")
        result = measure(
            layout_file=args.layout,
            report_file=args.report,
            image=args.image,
            photo=args.photo,
            corners_text=args.corners,
            reference_p95=args.reference_p95,
            annotated_file=args.annotated,
            warped_out_file=args.warped_out,
        )
    except MultiRoiLabError as error:
        print(f"multi-ROI Lab error: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
