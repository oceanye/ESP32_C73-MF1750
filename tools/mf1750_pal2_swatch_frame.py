#!/usr/bin/env python3
"""PAL2 production-path swatch frame + analysis kit generator; no live I/O.

PAL2 = palette calibration over the PRODUCTION OTP path (POST /api/frame ->
frozen stock driver; no runtime LUT, stock code semantics 0 black / 1 white /
2 yellow / 3 red / 5 blue / 6 green). The frame uses exactly the PAL1 grid
geometry (8 columns x 8 rows per side, column = code) so the PAL2 batch and
the PAL1 bright batch form a controlled L535-vs-OTP comparison: the six shared
code columns are byte-identical in both frames.

The canonical frame contract (host.epd_frame.validate_frame) and the
production firmware both reject codes 4 and 7, so columns 4 and 7 are filled
with white (code 1); the PAL1 comparison is per-code on columns 0/1/2/3/5/6
and is unaffected. The white reference column for session calibration is code
1 (columns 1 and 7 both carry it).

Outputs (O_EXCL): pal2.frame4bpp, analysis-kit/observations.blank.json +
analysis-kit/contract.json (the extraction analyzer's binding surface), and a
sealed report.json. The kit is NOT a firmware campaign package: PAL2's binding
is frame sha + sealed batch evidence, not a campaign contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.epd_frame import (  # noqa: E402
    ControllerMapping, controller_stream, validate_frame,
)
from host.static_photo import palette_cal_pal1 as pal1  # noqa: E402
from host.static_photo import lightness_history as base  # noqa: E402

KIND = "mf1750-pal2-swatch-frame-v1"
KIT_KIND = "mf1750-pal2-analysis-kit-v1"
DRIVE_CODES = (0, 1, 2, 3, 5, 6)
WHITE_FILL_CODES = (4, 7)
WHITE = 1
PRODUCTION_MAPPINGS = (ControllerMapping(0, False, False, False),
                       ControllerMapping(1, False, False, False))
PAL1_PACKAGE = ROOT / ".test-output/offline/PAL1_CAL_20260925_R2"


def frame() -> bytes:
    """PAL2 swatch frame: PAL1 geometry; columns 4/7 filled white."""
    value = bytearray([WHITE * 17]) * (base.WIDTH * base.HEIGHT // 2)
    for controller in range(2):
        for row in range(8):
            for column in range(8):
                code = column if column in DRIVE_CODES else WHITE
                stripe = bytes([code * 17]) * (base.CELL_W // 2)
                x = controller * base.HALF + base.X0 + column * (
                    base.CELL_W + base.GAP)
                y = base.Y0 + row * (base.CELL_H + base.GAP)
                for py in range(y, y + base.CELL_H):
                    start = py * (base.WIDTH // 2) + x // 2
                    value[start:start + base.CELL_W // 2] = stripe
    return bytes(value)


def blank_observations(contract_id: str, action_id: str, frame_sha: str) -> dict:
    rows = []
    for controller in ("CS1", "CS2"):
        for code in range(8):
            for row in range(8):
                rows.append({
                    "controller": controller,
                    "comparison_id": f"PAL2_C{code}",
                    "recipe_id": f"PAL2-C{code}-R{row}",
                    "position": ("T" if row < 4 else "B") + ("L" if code < 4 else "R"),
                    "roi": {
                        "x": base.X0 + code * (base.CELL_W + base.GAP),
                        "y": base.Y0 + row * (base.CELL_H + base.GAP),
                        "width": base.CELL_W, "height": base.CELL_H,
                    },
                    "lab": None, "noise": None, "quality_pass": None,
                    "single_pixel_uniform": None,
                    "measurement_evidence_sha256": None,
                    "drive_code": code if code in DRIVE_CODES else None,
                    "white_fill": code not in DRIVE_CODES,
                })
    return {
        "kind": "mf1750-pal2-blank-observations-v1",
        "history_contract_id": contract_id,
        "identity": {
            "test_phase": "SCREEN",
            "profile_id": "OTP_PRODUCTION_STOCK",
            "action_sha256": action_id,
            "frame_sha256": frame_sha,
            "source_state": "PAL1_BRIGHT_SCREEN_BISTABLE",
            "target_state": "PAL2_CAL",
        },
        "observations": rows,
    }


def build_kit(out: Path) -> dict:
    data = frame()
    validate_frame(data)  # canonical contract: 1024x600/4bpp, codes subset of 0/1/2/3/5/6
    identity = pal1.payload_identity(data, True)
    descriptor = {
        "campaign": "PAL2_PRODUCTION_OTP_20260925",
        "frame_sha256": identity["sha256"],
        "geometry": "PAL1 grid 8x8 per side, column=code, columns 4/7 white-filled",
    }
    descriptor_id = pal1.digest(pal1.canonical(descriptor))
    action_id = pal1.digest(f"PAL2_PRODUCTION_OTP_20260925|1|{descriptor_id}".encode())
    cs1 = pal1.payload_identity(controller_stream(data, PRODUCTION_MAPPINGS[0]))
    cs2 = pal1.payload_identity(controller_stream(data, PRODUCTION_MAPPINGS[1]))
    contract = {
        "kind": KIT_KIND,
        "campaign_id": "PAL2_PRODUCTION_OTP_20260925",
        "production_path": "POST /api/frame -> frozen stock OTP driver; no "
                           "runtime LUT; stock code semantics; 4bpp nibble "
                           "straight to DTM",
        "codes_4_and_7_white_filled": True,
        "codes_4_7_rejected_by_canonical_contract_and_firmware": True,
        "actions": [{
            "ordinal": 1, "stage": "PAL2", "role": "PAL2_CAL",
            "driver_entry": "production /api/frame",
            "profile_id": "OTP_PRODUCTION_STOCK",
            "descriptor_id": descriptor_id, "action_id": action_id,
            "frame": identity, "cs1_dtm": cs1, "cs2_dtm": cs2,
            "prior_action_id": None,
            "visible_refresh_count": 1, "waveform_internal_phase": "OPAQUE",
            "source_state": "PAL1_BRIGHT_SCREEN_BISTABLE",
            "target_state": "PAL2_CAL", "global_header": "stock",
        }],
        "action_count": 1,
        "qualified_count": 0, "live_ready": False,
        "not_a_campaign_package": True,
    }
    contract["contract_id"] = pal1.digest(pal1.canonical(contract))
    kit = out / "analysis-kit"
    kit.mkdir()
    (kit / "contract.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (kit / "observations.blank.json").write_text(
        json.dumps(blank_observations(contract["contract_id"], action_id,
                                      identity["sha256"]),
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "pal2.frame4bpp").write_bytes(data)
    return contract


def pal1_column_comparison(pal1_frame_path: Path, pal2: bytes) -> dict:
    """Byte equality of the six shared code columns vs the PAL1 frame."""
    if not pal1_frame_path.is_file():
        return {"status": "PAL1_PACKAGE_FRAME_ABSENT"}
    pal1_frame = pal1_frame_path.read_bytes()
    rows = []
    for code in DRIVE_CODES:
        same = True
        for controller in range(2):
            x = controller * base.HALF + base.X0 + code * (base.CELL_W + base.GAP)
            for row in range(8):
                y = base.Y0 + row * (base.CELL_H + base.GAP)
                for py in range(y, y + base.CELL_H):
                    start = py * (base.WIDTH // 2) + x // 2
                    span = slice(start, start + base.CELL_W // 2)
                    if pal1_frame[span] != pal2[span]:
                        same = False
        rows.append({"code": code, "byte_identical_to_pal1_column": same})
    return {"status": "PASS" if all(r["byte_identical_to_pal1_column"]
                                    for r in rows) else "MISMATCH",
            "columns": rows,
            "note": "same pixels driven on the six shared columns; the "
                    "waveform path (L535 vs OTP) is the only independent "
                    "variable vs the PAL1 bright batch",
            "pal1_frame": {"path": str(pal1_frame_path.resolve()),
                           "sha256": hashlib.sha256(pal1_frame).hexdigest()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pal1-frame", type=Path,
                        default=PAL1_PACKAGE / "pal1.frame4bpp")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if out.exists():
        raise SystemExit("output dir must not exist (O_EXCL batch)")
    out.mkdir(parents=True, exist_ok=False)
    contract = build_kit(out)
    data = (out / "pal2.frame4bpp").read_bytes()
    report = {
        "kind": KIND,
        "frame": contract["actions"][0]["frame"],
        "cs1_dtm": contract["actions"][0]["cs1_dtm"],
        "cs2_dtm": contract["actions"][0]["cs2_dtm"],
        "contract_id": contract["contract_id"],
        "action_id": contract["actions"][0]["action_id"],
        "drive_codes": list(DRIVE_CODES),
        "white_fill_codes": list(WHITE_FILL_CODES),
        "canonical_validate_frame": "PASS",
        "production_mappings": [
            {"controller": "CS1", "mapping": {"source_half": 0, "flip_x": False,
                                              "flip_y": False, "nibble_swap": False}},
            {"controller": "CS2", "mapping": {"source_half": 1, "flip_x": False,
                                              "flip_y": False, "nibble_swap": False}},
        ],
        "pal1_column_comparison": pal1_column_comparison(args.pal1_frame, data),
        "hardware_accessed": False,
        "qualified_count": 0,
    }
    report["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(pal1.canonical(report)).hexdigest(),
    }
    (out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "PASS", "output": str(out),
                      "contract_id": contract["contract_id"],
                      "frame_sha256": report["frame"]["sha256"],
                      "hardware_accessed": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
