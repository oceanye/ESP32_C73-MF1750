#!/usr/bin/env python3
"""From-white spectrum v0: the measured 8 commented endpoints as family ladders.

Pure offline analysis over the sealed MIDDLE-chain extraction (bright session
2026-09-17). The from-white commented drive has exactly 8 codes; all 8
endpoints are measured here. Families follow the frozen 12-family convention
(30-degree hue sectors, R centered at 0/360); ladder chaining applies the
frozen gates (in-chain dL*>=2, dE00>=3, hue delta <=5 degrees, noise floor
max(5xMAD, CI95 half-width)). Camera-relative Lab; qualified stays 0.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.color_pipeline.color import delta_e_ciede2000, lab_to_srgb8  # noqa: E402
from host.static_photo import lightness_test as optical  # noqa: E402

EXTRACTION = ROOT / ".test-output/offline/LH1_REBOUND_MIDDLE_20260917_ANALYSIS_V1/extraction.json"
DEFAULT_OUT = ROOT / ".test-output/offline/FROM_WHITE_SPECTRUM_20260918_V1"
FAMILY_IDS = ("R", "RO", "O", "Y", "YG", "G", "T", "C", "B", "I", "V", "M")
NEUTRAL_CHROMA_MAX = 14.0  # M7 white measures C*=12; M6 cyan C*=14.4 stays chromatic


def canon(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def seal(value: dict) -> dict:
    return {**value, "integrity": {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(canon(value)).hexdigest()}}


def write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def bind(path: Path) -> dict:
    data = Path(path).read_bytes()
    return {"path": str(Path(path).resolve()), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def family_of(hue_deg: float, chroma: float) -> str:
    if chroma < NEUTRAL_CHROMA_MAX:
        return "NEUTRAL"
    sector = int((hue_deg + 15.0) % 360 // 30)
    return FAMILY_IDS[sector]


def delta_e00(a, b) -> float:
    return delta_e_ciede2000(a, b)


def extract_endpoints(extraction: dict) -> list[dict]:
    per_recipe = defaultdict(list)
    for row in extraction["rows"]:
        if row.get("quality_pass") and row.get("lab_median"):
            per_recipe[(row["controller"], row["recipe_id"])].append(row)
    endpoints = {}
    for (controller, recipe), rows in sorted(per_recipe.items()):
        labs = [r["lab_median"] for r in rows]
        median = [sorted(c)[len(c) // 2] for c in zip(*labs)]
        spread = max(c[0] for c in labs) - min(c[0] for c in labs)
        noise = max(max(5.0 * r["lstar_mad"], r["lstar_ci95_half_width"])
                    for r in rows)
        endpoints.setdefault(recipe.split("-")[2], {})[controller] = {
            "lab": median, "lstar_position_spread": spread,
            "lstar_noise_floor": noise, "positions": len(rows)}
    result = []
    for code_key, sides in sorted(endpoints.items()):
        # CS1 is the position-consistent reference side (all 4 positions pass);
        # CS2 enters as a cross-check only where its quality gate passed (the
        # sealed MIDDLE review holds most CS2 cells POSITION_DEPENDENT).
        if "CS1" not in sides or sides["CS1"]["positions"] != 4:
            raise ValueError(f"{code_key} CS1 reference positions incomplete")
        lab = sides["CS1"]["lab"]
        chroma = math.hypot(lab[1], lab[2])
        hue = math.degrees(math.atan2(lab[2], lab[1])) % 360.0
        cs2 = sides.get("CS2")
        result.append({
            "middle_code": int(code_key[1:]),
            "recipe_prefix": code_key,
            "lab_cross_controller_mean": lab,
            "reference_side": "CS1",
            "lstar_cs1": sides["CS1"]["lab"][0],
            "lstar_cs2": cs2["lab"][0] if cs2 else None,
            "cs2_quality_positions": cs2["positions"] if cs2 else 0,
            "chroma": chroma, "hue_degrees": hue,
            "family": family_of(hue, chroma),
            "lstar_position_spread_max": sides["CS1"]["lstar_position_spread"],
            "lstar_noise_floor": sides["CS1"]["lstar_noise_floor"],
        })
    return result


def chain_ladders(endpoints: list[dict]) -> list[dict]:
    """Per family: order by L*, chain adjacent levels under the frozen gates."""
    gates = optical.THRESHOLDS
    ladders = []
    for family in list(FAMILY_IDS) + ["NEUTRAL"]:
        members = sorted((e for e in endpoints if e["family"] == family),
                         key=lambda e: e["lab_cross_controller_mean"][0])
        if not members:
            continue
        levels = [members[0]]
        breaks = []
        for prev, cur in zip(members, members[1:]):
            a, b = prev["lab_cross_controller_mean"], cur["lab_cross_controller_mean"]
            dl = abs(b[0] - a[0])
            dh = abs(cur["hue_degrees"] - prev["hue_degrees"])
            dh = min(dh, 360.0 - dh)
            if family == "NEUTRAL":
                dh = 0.0  # neutral axis: hue gate not meaningful (frozen convention)
            de00 = delta_e00(a, b)
            noise = max(prev["lstar_noise_floor"], cur["lstar_noise_floor"])
            ok = (dl >= max(2.0, noise) and (de00 is None or de00 >= 3.0)
                  and dh <= gates["maximum_hue_difference_degrees"])
            if ok:
                levels.append(cur)
            else:
                breaks.append({"from_code": prev["middle_code"],
                               "to_code": cur["middle_code"],
                               "delta_l": dl, "delta_e00": de00,
                               "delta_hue_degrees": dh, "noise_floor": noise})
        ladders.append({
            "family": family, "level_count": len(levels),
            "member_count": len(members),
            "ladder": [{"middle_code": e["middle_code"],
                        "lab": e["lab_cross_controller_mean"],
                        "hue_degrees": e["hue_degrees"]} for e in levels],
            "unchained_members": [e["middle_code"] for e in members
                                  if e not in levels],
            "chain_breaks": breaks})
    return ladders


def render_png(path: Path, ladders: list[dict]) -> None:
    from PIL import Image, ImageDraw
    cell, margin, label_w = 72, 20, 110
    rows = [l for l in ladders]
    width = margin * 2 + label_w + cell * max(len(l["ladder"]) for l in rows)
    height = margin * 2 + cell * len(rows) + 30
    img = Image.new("RGB", (width, height), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    draw.text((margin, 4),
              "From-white spectrum v0 (2026-09-17 bright session, camera-relative)",
              fill=(0, 0, 0))
    for row, ladder in enumerate(rows):
        y = margin + 24 + row * cell
        draw.text((margin, y + cell // 3),
                  f"{ladder['family']} x{ladder['level_count']}", fill=(0, 0, 0))
        for col, level in enumerate(ladder["ladder"]):
            rgb = lab_to_srgb8(level["lab"])
            x = margin + label_w + col * cell
            draw.rectangle([x, y, x + cell - 6, y + cell - 6], fill=rgb)
            draw.text((x + 2, y + 2), f"M{level['middle_code']}",
                      fill=(255, 255, 255) if level["lab"][0] < 50 else (0, 0, 0))
            draw.text((x + 2, y + cell - 22), f"{level['lab'][0]:.0f}",
                      fill=(255, 255, 255) if level["lab"][0] < 50 else (0, 0, 0))
    img.save(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    extraction = json.loads(EXTRACTION.read_text(encoding="utf-8"))
    endpoints = extract_endpoints(extraction)
    ladders = chain_ladders(endpoints)
    png = out / "spectrum.png"
    render_png(png, ladders)
    report = seal({
        "kind": "mf1750-from-white-spectrum-v1",
        "source_extraction": bind(EXTRACTION),
        "session": "2026-09-17 bright (screen white L*~65.8)",
        "camera_relative_only": True, "calibrated_lab": False,
        "qualified_count": 0,
        "gates": {"delta_l_min": 2.0, "delta_e00_min": 3.0,
                  "hue_delta_max_degrees": 5.0,
                  "noise_floor": "max(5xMAD, CI95 half-width) per rung",
                  "neutral_axis_hue_gate": "not applicable"},
        "family_convention": "12 x 30-degree hue sectors, R centered 0/360; NEUTRAL if C*<14",
        "endpoints": endpoints,
        "ladders": ladders,
        "level_counts": {l["family"]: l["level_count"] for l in ladders},
        "from_white_code_space_exhausted": True,
        "note": "All 8 from-white commented codes measured; more levels need MAP mid-states (bright re-shoot pending) or the dose axis.",
        "spectrum_png": bind(png),
    })
    write_new(out / "spectrum.json", canon(report) + b"\n")
    print(json.dumps({"result": "PASS", "output": str(out),
                      "level_counts": report["level_counts"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
