"""LH3 dose-axis history screen: 8 code columns x 8 row repeats per side.

No I/O. Variant of the LH2 drive-map algorithm on the same 3-action chain:
SOURCE (active C7 white) -> DOSE1 (commented; column c of each side's 8x8 grid
carries code c in all 8 rows, so every code gets 8 spatial repeats per side)
-> DOSE2 (commented; frame byte-identical to DOSE1, so the only independent
variable between the two actions is one extra same-code application).

Design: docs/MF1750_LH3_DOSE_CHAIN_DESIGN_2026-09-21.md.
The 8 code columns are candidates, not encoded lightness ranks.
"""

from __future__ import annotations

from functools import lru_cache

from . import lightness_history as base

TEST_ID = "MF1750_LIGHTNESS_HISTORY_LH3_DOSE_V1_20260921"
STAGES = ("SOURCE", "DOSE1", "DOSE2")
HEADERS = ("active", "commented", "commented")
# DOSE frame rule: cell (row, column) carries code == column. Rows are spatial
# repeats of the same dose; code 7's column doubles as the commented white
# reference inside the chain.

canonical = base.canonical
digest = base.digest
placement = base.placement
controller_stream = base.controller_stream
payload_identity = base.payload_identity


def dose_code(row: int, column: int) -> int:
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
                "recipe_id": f"LH3D-S7-D{code}",
                "source": {"global_header": "active", "code": 7},
                "dose1": {"global_header": "commented", "code": code},
                "dose2": {"global_header": "commented", "code": code},
                "positions": positions,
                "repeats_per_controller": 8,
                "spatial_dither": False,
            }
        )
    return result


@lru_cache(maxsize=3)
def frame(stage):
    if stage not in STAGES:
        raise ValueError("only SOURCE/DOSE1/DOSE2; no repeat or white action")
    value = bytearray([0x77]) * (base.WIDTH * base.HEIGHT // 2)
    for controller in range(2):
        for row in range(8):
            for column in range(8):
                code = 7 if stage == "SOURCE" else dose_code(row, column)
                stripe = bytes([code * 17]) * (base.CELL_W // 2)
                x = controller * base.HALF + base.X0 + column * (
                    base.CELL_W + base.GAP
                )
                y = base.Y0 + row * (base.CELL_H + base.GAP)
                for py in range(y, y + base.CELL_H):
                    start = py * (base.WIDTH // 2) + x // 2
                    value[start : start + base.CELL_W // 2] = stripe
    result = bytes(value)
    if stage == "DOSE2":
        # The dose-axis independent variable requires identical frames: the
        # only difference between DOSE1 and DOSE2 is one prior application.
        assert result == frame("DOSE1"), "DOSE2 frame must equal DOSE1 frame"
    return result


assert frame("DOSE2") == frame("DOSE1"), "DOSE2/DOSE1 frame equality is structural"


def blank_observations(contract):
    # One observation per (side, code column, cell): 2 sides x 8 columns x 8
    # rows = 128 slots. Position labels follow the physical quadrant schema of
    # the optical analyzer; the row index lives in the recipe_id suffix so
    # every (controller, comparison, recipe, position) key stays unique.
    value = base.optical.blank_observations([])
    rows = []
    for info in recipes():
        code = info["dose1"]["code"]
        for controller in ("CS1", "CS2"):
            for position in info["positions"][controller.lower()]:
                r, c = position["row"], position["column"]
                rows.append(
                    {
                        "controller": controller,
                        "comparison_id": f"DOSE_C{code}",
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
    target = contract["actions"][2]
    value["identity"].update(
        test_phase="SCREEN",
        profile_id=target["profile_id"],
        action_sha256=target["action_id"],
        frame_sha256=target["frame"]["sha256"],
        source_state="LH3_DOSE1",
        target_state="LH3_DOSE2",
    )
    return value


def analyze_bound(value, contract):
    """Bind observations to the exact generated dose matrix before screening."""
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
            raise ValueError(f"dose identity mismatch: {key}")

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
        raise ValueError("128 controller-local dose cell/ROI slots must exactly match")
    report = base.optical.analyze_observations(base.deepcopy(value))
    report.pop("integrity")
    report.update(
        history_contract_id=contract["contract_id"],
        dose_codes=8,
        rows_per_dose_code_per_controller=8,
        dose2_frame_byte_identical_to_dose1=True,
    )
    return base.optical.attach_integrity(report)
