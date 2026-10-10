"""LH2 drive-map history screen: 8 middle histories x 8 map codes per side.

No I/O. Variant of the LH1 history algorithm: SOURCE (active C7 white) ->
MIDDLE (commented M0..M7, rebuilds the eight measured histories) -> MAP
(commented; each recipe's four quadrant cells receive the four codes of its
assigned half, so every (history, code) pair appears exactly once per side).

Design: docs/MF1750_LH2_DRIVE_MAP_CHAIN_DESIGN_2026-09-17.md.
The 16 recipes are candidates, not encoded lightness ranks.
"""

from __future__ import annotations

from functools import lru_cache

from . import lightness_history as base

TEST_ID = "MF1750_LIGHTNESS_HISTORY_LH2_DRIVE_MAP_V1_20260917"
STAGES = ("SOURCE", "MIDDLE", "MAP")
HEADERS = ("active", "commented", "commented")
# MAP frame rule: recipe (m, h) writes code 4*h + quadrant_index at its cell in
# quadrant q (TL=0, TR=1, BL=2, BR=3). Every (history m, code) pair then appears
# exactly once per side; every code occupies exactly 8 cells per side.

canonical = base.canonical
digest = base.digest
placement = base.placement
controller_stream = base.controller_stream
payload_identity = base.payload_identity


def recipe_parts(recipe: int) -> tuple[int, int]:
    return recipe % 8, recipe // 8


def map_code(recipe: int, row: int, column: int) -> int:
    m, h = recipe_parts(recipe)
    if not (0 <= m < 8 and 0 <= h < 2 and 0 <= row < 8 and 0 <= column < 8):
        raise ValueError("recipe/cell out of range")
    quadrant = (2 if row >= 4 else 0) + (1 if column >= 4 else 0)
    return 4 * h + quadrant


def recipes() -> list[dict]:
    result = []
    for recipe in range(16):
        m, h = recipe_parts(recipe)
        positions = {}
        for name, cells in zip(("cs1", "cs2"), placement(), strict=True):
            positions[name] = []
            for index, number in enumerate(cells):
                if number == recipe:
                    r, c = divmod(index, 8)
                    positions[name].append(
                        {
                            "row": r,
                            "column": c,
                            "local_roi": {
                                "x": base.X0 + c * (base.CELL_W + base.GAP),
                                "y": base.Y0 + r * (base.CELL_H + base.GAP),
                                "width": base.CELL_W,
                                "height": base.CELL_H,
                            },
                        }
                    )
        result.append(
            {
                "recipe_id": f"LH2-S7-M{m}-H{h}",
                "source": {"global_header": "active", "code": 7},
                "middle": {"global_header": "commented", "code": m},
                "map": {
                    "global_header": "commented",
                    "code_half": h,
                    "codes_by_quadrant": {"TL": 4 * h, "TR": 4 * h + 1,
                                          "BL": 4 * h + 2, "BR": 4 * h + 3},
                },
                "positions": positions,
                "repeats_per_controller": 4,
                "spatial_dither": False,
            }
        )
    return result


@lru_cache(maxsize=3)
def frame(stage):
    if stage not in STAGES:
        raise ValueError("only SOURCE/MIDDLE/MAP; no repeat or white action")
    value = bytearray([0x77]) * (base.WIDTH * base.HEIGHT // 2)
    for controller, cells in enumerate(placement()):
        for index, recipe in enumerate(cells):
            row, column = divmod(index, 8)
            code = (
                7
                if stage == "SOURCE"
                else recipe % 8
                if stage == "MIDDLE"
                else map_code(recipe, row, column)
            )
            stripe = bytes([code * 17]) * (base.CELL_W // 2)
            x = controller * base.HALF + base.X0 + column * (base.CELL_W + base.GAP)
            y = base.Y0 + row * (base.CELL_H + base.GAP)
            for py in range(y, y + base.CELL_H):
                start = py * (base.WIDTH // 2) + x // 2
                value[start : start + base.CELL_W // 2] = stripe
    return bytes(value)


def blank_observations(contract):
    # MAP rows are keyed by the exact code each cell carries; every (history,
    # code) pair appears once per side, so there are no four-quadrant spatial
    # replicas of one condition and comparison groups are single-position.
    value = base.optical.blank_observations([])
    rows = []
    for recipe, info in enumerate(recipes()):
        for controller in ("CS1", "CS2"):
            for position in info["positions"][controller.lower()]:
                r, c = position["row"], position["column"]
                rows.append(
                    {
                        "controller": controller,
                        "comparison_id": f"MAP_C{map_code(recipe, r, c)}",
                        "recipe_id": info["recipe_id"],
                        "position": ("T" if r < 4 else "B") + ("L" if c < 4 else "R"),
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
        source_state="LH2_MIDDLE",
        target_state="LH2_MAP",
    )
    return value


def analyze_bound(value, contract):
    """Bind observations to the exact generated map matrix before screening."""
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
            raise ValueError(f"map identity mismatch: {key}")

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
        raise ValueError("128 controller-local recipe/ROI slots must exactly match")
    report = base.optical.analyze_observations(base.deepcopy(value))
    report.pop("integrity")
    report.update(
        history_contract_id=contract["contract_id"],
        recipe_count_per_map_code=2,
        histories_per_map_code=8,
    )
    return base.optical.attach_integrity(report)
