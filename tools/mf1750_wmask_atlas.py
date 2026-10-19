#!/usr/bin/env python3
"""Build an offline MF1750 White-record mask contact sheet.

Each repeated --cell argument is BATCH_DIR|LABEL|MASK|STEM[|TIME].  TIME
 defaults to t0.  The tool reads exactly STEM-TIME-warped.jpg, STEM-lab.json,
and STEM-diagnostic.json; it never searches for substitute evidence names.
Numeric masks sort ascending (00, 01, ... 0F, then higher conceptual masks);
registered GrayExt family labels 1C/1D/1E follow while retaining input order,
then explicit 0E_R0/0E_R1/0E_R2/0E_R3 single-record family labels, then
explicit 0E_R0R1/0E_R0R2/0E_R0R3 record-pair family labels, and other
non-numeric references come last.  GrayExt labels mean a low-4-bit base plus
the whole records 0-3 group; 0E_R* labels mean base 0E plus exactly one
records 0-3 member; 0E_R*R* labels mean base 0E plus exactly the listed
records 0-3 pair.  None of these family labels is interpreted as a bitmask.
Missing warped/Lab/diagnostic evidence skips that cell and is reported.

To extend an atlas, add another --cell and select a new --output-dir.  The
output directory and every artifact are created exclusively (O_EXCL semantics).
Only Pillow and the Python standard library are used.  No hardware, serial,
relay, network, camera, or flashing access is performed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
import io
import json
import math
from pathlib import Path
import re
from typing import Any, Sequence

from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True)
class CellSpec:
    batch_dir: Path
    label: str
    mask: str
    stem: str
    time: str
    input_index: int


class AtlasError(ValueError):
    """Raised for invalid atlas inputs or malformed existing evidence."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _pretty(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_new(path: Path, payload: bytes) -> None:
    with path.open("xb") as destination:
        destination.write(payload)


def _parse_cell(value: str, input_index: int) -> CellSpec:
    parts = value.split("|")
    if len(parts) not in (4, 5) or any(not part.strip() for part in parts):
        raise AtlasError(
            "--cell must be BATCH_DIR|LABEL|MASK|STEM[|TIME] with non-empty fields"
        )
    batch, label, mask, stem = (part.strip() for part in parts[:4])
    time = parts[4].strip() if len(parts) == 5 else "t0"
    if not re.fullmatch(r"t[0-9]+", time):
        raise AtlasError(f"invalid cell time {time!r}; expected t0, t60, t300, ...")
    return CellSpec(Path(batch), label, mask, stem, time, input_index)


GRAYEXT_FAMILY_LABELS = frozenset({"1C", "1D", "1E"})
SINGLE_RECORD_FAMILY_LABELS = frozenset({"0E_R0", "0E_R1", "0E_R2", "0E_R3"})
RECORD_SUBSET_FAMILY_LABELS = frozenset({"0E_R0R1", "0E_R0R2", "0E_R0R3"})
FAMILY_LABELS = (
    GRAYEXT_FAMILY_LABELS | SINGLE_RECORD_FAMILY_LABELS | RECORD_SUBSET_FAMILY_LABELS
)


def _mask_sort_key(cell: CellSpec) -> tuple[int, int, int]:
    text = cell.mask.strip()
    if text in GRAYEXT_FAMILY_LABELS:
        return 1, cell.input_index, cell.input_index
    if text in SINGLE_RECORD_FAMILY_LABELS:
        return 2, cell.input_index, cell.input_index
    if text in RECORD_SUBSET_FAMILY_LABELS:
        return 3, cell.input_index, cell.input_index
    if re.fullmatch(r"(?:0[xX])?[0-9A-Fa-f]+", text):
        value = int(text[2:] if text.lower().startswith("0x") else text, 16)
        return 0, value, cell.input_index
    return 4, cell.input_index, cell.input_index


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AtlasError(f"cannot read {label} {path}: {error}") from error
    if not isinstance(payload, dict):
        raise AtlasError(f"{label} must contain a JSON object: {path}")
    return payload


def _number(payload: dict[str, Any], key: str, path: Path) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AtlasError(f"missing or non-numeric {key} in {path}")
    return float(value)


def _source_record(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "name": path.name,
        "bytes": len(payload),
        "sha256": _sha256(payload),
    }


def _load_cell(
    spec: CellSpec, roi_width: float, roi_height: float
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, Image.Image | None]:
    batch = spec.batch_dir.resolve()
    photo = batch / f"{spec.stem}-{spec.time}-warped.jpg"
    lab_path = batch / f"{spec.stem}-lab.json"
    diagnostic_path = batch / f"{spec.stem}-diagnostic.json"
    expected = {
        "batch_dir": str(batch),
        "photo": str(photo),
        "lab": str(lab_path),
        "diagnostic": str(diagnostic_path),
    }
    missing = [
        f"missing_{role}"
        for role, path in (
            ("warped", photo),
            ("lab", lab_path),
            ("diagnostic", diagnostic_path),
        )
        if not path.is_file()
    ]
    if missing:
        return None, {
            "label": spec.label,
            "mask": spec.mask,
            "stem": spec.stem,
            "time": spec.time,
            "reasons": missing,
            "expected": expected,
        }, None

    lab_document = _load_json(lab_path, "Lab")
    lab_key = f"{spec.stem}-{spec.time}"
    lab = lab_document.get(lab_key)
    if not isinstance(lab, dict):
        return None, {
            "label": spec.label,
            "mask": spec.mask,
            "stem": spec.stem,
            "time": spec.time,
            "reasons": [f"missing_lab_key:{lab_key}"],
            "expected": expected,
        }, None
    diagnostic = _load_json(diagnostic_path, "diagnostic")
    drf_ms = _number(diagnostic, "drf_ms", diagnostic_path)
    values = {key: _number(lab, key, lab_path) for key in ("L", "a", "b", "std_L")}

    with Image.open(photo) as source:
        source.load()
        image = source.convert("RGB")
    width, height = image.size
    crop_width = max(1, round(width * roi_width))
    crop_height = max(1, round(height * roi_height))
    left = (width - crop_width) // 2
    top = (height - crop_height) // 2
    right = left + crop_width
    bottom = top + crop_height
    crop = image.crop((left, top, right, bottom))
    record = {
        "label": spec.label,
        "mask": spec.mask,
        "time": spec.time,
        "batch": batch.name,
        "batch_dir": str(batch),
        "photo": str(photo),
        "photo_name": photo.name,
        "lab_key": lab_key,
        "lab": {
            **values,
            "captured_at": lab.get("captured_at"),
        },
        "drf_ms": int(drf_ms) if drf_ms.is_integer() else drf_ms,
        "source_size": [width, height],
        "crop_pixels": [left, top, right, bottom],
        "crop_normalized": [
            left / width,
            top / height,
            right / width,
            bottom / height,
        ],
        "sources": {
            "photo": _source_record(photo),
            "lab": _source_record(lab_path),
            "diagnostic": _source_record(diagnostic_path),
        },
    }
    return record, None, crop


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _render_sheet(
    cells: list[dict[str, Any]],
    crops: list[Image.Image],
    *,
    columns: int,
    cell_width: int,
    cell_height: int,
    roi_width: float,
    roi_height: float,
    title: str,
) -> Image.Image:
    margin = 20
    gap = 16
    title_height = 64
    text_height = 110
    rows = math.ceil(len(cells) / columns)
    sheet_width = margin * 2 + columns * cell_width + (columns - 1) * gap
    sheet_height = (
        margin * 2
        + title_height
        + rows * (cell_height + text_height)
        + (rows - 1) * gap
    )
    sheet = Image.new("RGB", (sheet_width, sheet_height), (244, 246, 250))
    draw = ImageDraw.Draw(sheet)
    title_font = _font(30)
    label_font = _font(24)
    metric_font = _font(21)
    draw.text(
        (margin, margin),
        f"{title} | {len(cells)} cells | central ROI {roi_width:.0%} x {roi_height:.0%}",
        fill=(18, 26, 38),
        font=title_font,
    )

    for index, (cell, crop) in enumerate(zip(cells, crops)):
        row, column = divmod(index, columns)
        x = margin + column * (cell_width + gap)
        y = margin + title_height + row * (cell_height + text_height + gap)
        resized = crop.resize((cell_width, cell_height), Image.Resampling.LANCZOS)
        sheet.paste(resized, (x, y))
        draw.rectangle(
            (x, y, x + cell_width - 1, y + cell_height - 1),
            outline=(75, 82, 94),
            width=2,
        )
        lab = cell["lab"]
        mask_caption = "family" if cell["mask"] in FAMILY_LABELS else "mask"
        draw.text(
            (x + 4, y + cell_height + 8),
            f"{cell['label']} | {mask_caption} {cell['mask']} | {cell['time']}",
            fill=(15, 22, 32),
            font=label_font,
        )
        draw.text(
            (x + 4, y + cell_height + 42),
            f"L{lab['L']:.2f} a{lab['a']:.2f} b{lab['b']:.2f} std_L{lab['std_L']:.2f}",
            fill=(15, 22, 32),
            font=metric_font,
        )
        draw.text(
            (x + 4, y + cell_height + 74),
            f"drf_ms {cell['drf_ms']}",
            fill=(15, 22, 32),
            font=metric_font,
        )
    return sheet


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cell", action="append", required=True, metavar="BATCH|LABEL|MASK|STEM[|TIME]")
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--cell-width", type=int, default=640)
    parser.add_argument("--cell-height", type=int, default=360)
    parser.add_argument("--roi", type=float, nargs=2, default=(0.60, 0.60), metavar=("WIDTH", "HEIGHT"))
    parser.add_argument("--title", default="MF1750 White-record mask atlas")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.columns < 1 or args.cell_width < 64 or args.cell_height < 64:
        raise SystemExit("columns must be positive and cell dimensions at least 64")
    roi_width, roi_height = args.roi
    if not 0 < roi_width <= 1 or not 0 < roi_height <= 1:
        raise SystemExit("ROI fractions must be in (0, 1]")
    if args.output_dir.exists():
        raise SystemExit(f"output directory already exists: {args.output_dir}")

    specs = sorted(
        (_parse_cell(value, index) for index, value in enumerate(args.cell)),
        key=_mask_sort_key,
    )
    cells: list[dict[str, Any]] = []
    crops: list[Image.Image] = []
    skipped: list[dict[str, Any]] = []
    for spec in specs:
        cell, skip, crop = _load_cell(spec, roi_width, roi_height)
        if skip is not None:
            skipped.append(skip)
            continue
        if cell is None or crop is None:
            raise AtlasError("internal cell load contract failed")
        cells.append(cell)
        crops.append(crop)
    if not cells:
        raise SystemExit("no cells have complete warped/Lab/diagnostic evidence")

    sheet = _render_sheet(
        cells,
        crops,
        columns=args.columns,
        cell_width=args.cell_width,
        cell_height=args.cell_height,
        roi_width=roi_width,
        roi_height=roi_height,
        title=args.title,
    )
    png_buffer = io.BytesIO()
    sheet.save(png_buffer, format="PNG")
    png_payload = png_buffer.getvalue()
    jpg_buffer = io.BytesIO()
    sheet.save(jpg_buffer, format="JPEG", quality=95, subsampling=0)
    jpg_payload = jpg_buffer.getvalue()

    atlas = {
        "schema_version": 1,
        "kind": "mf1750-wmask-contact-sheet-atlas",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "offline_only": True,
        "title": args.title,
        "layout": {
            "columns": args.columns,
            "rows": math.ceil(len(cells) / args.columns),
            "cell_image_size": [args.cell_width, args.cell_height],
            "sheet_size": list(sheet.size),
            "numeric_masks_sorted_ascending": True,
            "grayext_family_labels_after_numeric_masks": True,
            "grayext_family_labels": sorted(GRAYEXT_FAMILY_LABELS),
            "grayext_family_label_semantics": (
                "low-4-bit base plus the whole records 0-3 group; not bitmasks"
            ),
            "single_record_family_labels_after_grayext": True,
            "single_record_family_labels": sorted(SINGLE_RECORD_FAMILY_LABELS),
            "single_record_family_label_semantics": (
                "base 0E plus exactly one records 0-3 member; not bitmasks"
            ),
            "record_subset_family_labels_after_single_record": True,
            "record_subset_family_labels": sorted(RECORD_SUBSET_FAMILY_LABELS),
            "record_subset_family_label_semantics": (
                "base 0E plus exactly the listed records 0-3 pair; not bitmasks"
            ),
            "family_labels_are_not_interpreted_as_hex_masks": True,
            "other_non_numeric_references_last": True,
        },
        "central_roi": {
            "width_fraction": roi_width,
            "height_fraction": roi_height,
            "same_relative_region_for_every_cell": True,
        },
        "requested_cell_count": len(specs),
        "rendered_cell_count": len(cells),
        "cells": cells,
        "skipped": skipped,
        "outputs": {
            "png": "wmask-atlas.png",
            "jpg": "wmask-atlas.jpg",
        },
    }
    atlas_payload = _pretty(atlas)
    artifacts = {
        "wmask-atlas.png": png_payload,
        "wmask-atlas.jpg": jpg_payload,
        "atlas.json": atlas_payload,
    }
    manifest = {
        "schema_version": 1,
        "kind": "mf1750-wmask-contact-sheet-manifest",
        "batch_id": args.output_dir.name,
        "created_at": atlas["created_at"],
        "offline_only": True,
        "tool": {
            "path": str(Path(__file__).resolve()),
            "sha256": _sha256(Path(__file__).read_bytes()),
        },
        "rendered_cell_count": len(cells),
        "skipped_cell_count": len(skipped),
        "files": [
            {"file": name, "bytes": len(payload), "sha256": _sha256(payload)}
            for name, payload in sorted(artifacts.items())
        ],
        "integrity": {
            "algorithm": "sha256-canonical-json-without-integrity",
            "sha256": "",
        },
    }
    unsigned = dict(manifest)
    unsigned.pop("integrity")
    manifest["integrity"]["sha256"] = _sha256(_canonical(unsigned))
    manifest_payload = _pretty(manifest)

    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=False, exist_ok=False)
    for name, payload in sorted(artifacts.items()):
        _write_new(args.output_dir / name, payload)
    _write_new(args.output_dir / "manifest.json", manifest_payload)

    print(json.dumps({
        "png": str((args.output_dir / "wmask-atlas.png").resolve()),
        "jpg": str((args.output_dir / "wmask-atlas.jpg").resolve()),
        "atlas_json": str((args.output_dir / "atlas.json").resolve()),
        "manifest": str((args.output_dir / "manifest.json").resolve()),
        "manifest_canonical_sha256": manifest["integrity"]["sha256"],
        "manifest_file_sha256": _sha256(manifest_payload),
        "rendered_cell_count": len(cells),
        "cells": [
            {
                "label": cell["label"],
                "mask": cell["mask"],
                "batch": cell["batch"],
                "photo": cell["photo_name"],
                "lab": cell["lab"],
                "drf_ms": cell["drf_ms"],
            }
            for cell in cells
        ],
        "skipped": skipped,
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
