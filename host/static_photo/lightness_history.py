"""Single-pixel history screen: fixed frame generation and bound optical analysis.

No I/O. The 16 recipes are candidates, not encoded lightness ranks. Each target
group has eight distinct histories. No formula claims an inverse L* waveform.
"""

from copy import deepcopy
from functools import lru_cache
import hashlib
import json

from . import lightness_test as optical

TEST_ID = "MF1750_LIGHTNESS_HISTORY_V1_20260911"
STAGES = ("SOURCE", "MIDDLE", "TARGET")
HEADERS = ("active", "commented", "active")
WIDTH, HEIGHT, HALF = 1024, 600, 512
X0, Y0, CELL_W, CELL_H, GAP = 68, 64, 40, 52, 8


def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def placement():
    quadrants = (
        tuple(range(16)),
        tuple(4 * r + (c + r) % 4 for r in range(4) for c in range(4)),
        tuple(4 * ((r + c) % 4) + c for r in range(4) for c in range(4)),
        tuple(reversed(range(16))),
    )
    cells = [None] * 64
    for mapping, (y0, x0) in zip(
        quadrants, ((0, 0), (0, 4), (4, 0), (4, 4)), strict=True
    ):
        for index, recipe in enumerate(mapping):
            r, c = divmod(index, 4)
            cells[(r + y0) * 8 + c + x0] = recipe
    return tuple(cells), tuple(reversed(cells))


def recipes():
    result = []
    for recipe in range(16):
        target = (3, 7)[recipe // 8]
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
                                "x": X0 + c * (CELL_W + GAP),
                                "y": Y0 + r * (CELL_H + GAP),
                                "width": CELL_W,
                                "height": CELL_H,
                            },
                        }
                    )
        result.append(
            {
                "recipe_id": f"LH1-S7-M{recipe % 8}-T{target}",
                "source": {"global_header": "active", "code": 7},
                "middle": {"global_header": "commented", "code": recipe % 8},
                "target": {"global_header": "active", "code": target},
                "positions": positions,
                "repeats_per_controller": 4,
                "spatial_dither": False,
            }
        )
    return result


@lru_cache(maxsize=3)
def frame(stage):
    if stage not in STAGES:
        raise ValueError("only SOURCE/MIDDLE/TARGET; no repeat or white action")
    value = bytearray([0x77]) * (WIDTH * HEIGHT // 2)
    for controller, cells in enumerate(placement()):
        for index, recipe in enumerate(cells):
            row, column = divmod(index, 8)
            code = (
                7
                if stage == "SOURCE"
                else recipe % 8
                if stage == "MIDDLE"
                else (3, 7)[recipe // 8]
            )
            stripe = bytes([code * 17]) * (CELL_W // 2)
            x = controller * HALF + X0 + column * (CELL_W + GAP)
            y = Y0 + row * (CELL_H + GAP)
            for py in range(y, y + CELL_H):
                start = py * (WIDTH // 2) + x // 2
                value[start : start + CELL_W // 2] = stripe
    return bytes(value)


def controller_stream(value, controller):
    if (
        len(value) != WIDTH * HEIGHT // 2
        or type(controller) is not int
        or controller not in (0, 1)
    ):
        raise ValueError("invalid frame or controller")
    return b"".join(
        value[y * 512 + controller * 256 : y * 512 + (controller + 1) * 256]
        for y in range(HEIGHT)
    )


def payload_identity(value, histogram=False):
    fnv = 2166136261
    for byte in value:
        fnv = ((fnv ^ byte) * 16777619) & 0xFFFFFFFF
    result = {"bytes": len(value), "sha256": digest(value), "fnv1a": fnv}
    if histogram:
        counts = [0] * 8
        for byte in value:
            counts[byte >> 4] += 1
            counts[byte & 15] += 1
        result["histogram"] = counts
    return result


def blank_observations(contract):
    value = optical.blank_observations(recipes())
    value["history_contract_id"] = contract["contract_id"]
    target = contract["actions"][2]
    value["identity"].update(
        test_phase="SCREEN",
        profile_id=target["profile_id"],
        action_sha256=target["action_id"],
        frame_sha256=target["frame"]["sha256"],
        source_state="LH1_MIDDLE",
        target_state="LH1_TARGET",
    )
    return value


def analyze_bound(value, contract):
    """Bind observations to the exact generated matrix before optical screening."""
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
            raise ValueError(f"target identity mismatch: {key}")

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
    report = optical.analyze_observations(deepcopy(value))
    report.pop("integrity")
    report.update(
        history_contract_id=contract["contract_id"],
        recipe_count_per_target=8,
        ten_levels_need_more_distinct_recipes=value["requested_levels"] == 10,
    )
    return optical.attach_integrity(report)
