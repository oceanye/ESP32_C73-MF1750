"""PAL1 measured-palette calibration screen: 8 code columns x 8 row repeats.

No I/O. Single-action variant of the LH3 dose layout: one PAL1 stage (active
global header, the production render path — same electrical path as the LH3
SOURCE action) painting column c of each side's 8x8 grid with code c in all 8
rows, so every code gets 8 spatial repeats per side. Codes 0/1/2/3/5/6 are
the physical palette colours; columns 4 and 7 are measured for the record
(code 7 is the session's white reference column).

Design: docs/MF1750_PAL1_MEASURED_PALETTE_CHAIN_DESIGN_2026-09-24.md.
"""

from __future__ import annotations

from functools import lru_cache

from . import lightness_history as base

TEST_ID = "MF1750_PALETTE_CAL_PAL1_V1_20260924"
STAGES = ("PAL1",)
HEADERS = ("active",)
# Frame rule: cell (row, column) carries code == column. Rows are spatial
# repeats; code 7's column is the session white reference.

canonical = base.canonical
digest = base.digest
placement = base.placement
controller_stream = base.controller_stream
payload_identity = base.payload_identity


def pal_code(row: int, column: int) -> int:
    if not (0 <= row < 8 and 0 <= column < 8):
        raise ValueError("cell out of range")
    return column


def recipes() -> list[dict]:
    result = []
    for code in range(8):
        positions = {}
        for name in ("cs1", "cs2"):
            positions[name] = [
                {
                    "row": row,
                    "column": code,
                    "local_roi": {
                        "x": base.X0 + code * (base.CELL_W + base.GAP),
                        "y": base.Y0 + row * (base.CELL_H + base.GAP),
                        "width": base.CELL_W,
                        "height": base.CELL_H,
                    },
                }
                for row in range(8)
            ]
        result.append(
            {
                "recipe_id": f"PAL1-C{code}",
                "pal1": {"global_header": "active", "code": code},
                "positions": positions,
                "repeats_per_controller": 8,
                "spatial_dither": False,
            }
        )
    return result


@lru_cache(maxsize=1)
def frame(stage):
    if stage not in STAGES:
        raise ValueError("only PAL1; single-action chain, no repeat or white action")
    value = bytearray([0x77]) * (base.WIDTH * base.HEIGHT // 2)
    for controller in range(2):
        for row in range(8):
            for column in range(8):
                code = pal_code(row, column)
                stripe = bytes([code * 17]) * (base.CELL_W // 2)
                x = controller * base.HALF + base.X0 + column * (
                    base.CELL_W + base.GAP
                )
                y = base.Y0 + row * (base.CELL_H + base.GAP)
                for py in range(y, y + base.CELL_H):
                    start = py * (base.WIDTH // 2) + x // 2
                    value[start : start + base.CELL_W // 2] = stripe
    return bytes(value)


def blank_observations(contract):
    # One observation per (side, code column, cell): 2 sides x 8 columns x 8
    # rows = 128 slots, same keying as the LH3 dose observations.
    value = base.optical.blank_observations([])
    rows = []
    for info in recipes():
        code = info["pal1"]["code"]
        for controller in ("CS1", "CS2"):
            for position in info["positions"][controller.lower()]:
                r, c = position["row"], position["column"]
                rows.append(
                    {
                        "controller": controller,
                        "comparison_id": f"PAL1_C{code}",
                        "recipe_id": f"{info['recipe_id']}-R{r}",
                        "position": ("T" if r < 4 else "B")
                        + ("L" if c < 4 else "R"),
                        "roi": position["local_roi"],
                        "lab": None,
                        "noise": None,
                        "quality_pass": None,
                        "single_pixel_uniform": None,
                        "measurement_evidence_sha256": None,
                    }
                )
    value["observations"] = rows
    value["history_contract_id"] = contract["contract_id"]
    action = contract["actions"][0]
    value["identity"].update(
        test_phase="SCREEN",
        profile_id=action["profile_id"],
        action_sha256=action["action_id"],
        frame_sha256=action["frame"]["sha256"],
        source_state="LH3_DOSE_V2_COMPLETE_SCREEN",
        target_state="PAL1_CAL",
    )
    return value


def analyze_bound(value, contract):
    """Bind observations to the exact generated PAL1 matrix before screening."""
    if value.get("history_contract_id") != contract["contract_id"]:
        raise ValueError("history contract mismatch")
    expected = blank_observations(contract)
    for key in (
        "profile_id",
        "action_sha256",
        "frame_sha256",
        "source_state",
        "target_state",
        "test_phase",
    ):
        if value["identity"].get(key) != expected["identity"][key]:
            raise ValueError(f"pal1 identity mismatch: {key}")

    def key(row):
        return (
            row["controller"],
            row["comparison_id"],
            row["recipe_id"],
            row["position"],
        )

    wanted = {key(r): r["roi"] for r in expected["observations"]}
    supplied = {key(r): r["roi"] for r in value["observations"]}
    if len(value["observations"]) != 128 or wanted != supplied:
        raise ValueError("128 controller-local PAL1 cell/ROI slots must exactly match")
    report = base.optical.analyze_observations(base.deepcopy(value))
    report.pop("integrity")
    report.update(
        history_contract_id=contract["contract_id"],
        pal1_codes=8,
        rows_per_code_per_controller=8,
        physical_palette_codes=[0, 1, 2, 3, 5, 6],
        record_only_codes=[4, 7],
    )
    return base.optical.attach_integrity(report)
