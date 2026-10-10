#!/usr/bin/env python3
"""Route the SPI-only TF/microSD interface on the frozen R13 staging PCB.

Operating mode: REVISION.  The SHA-bound R13 PCB is the sole geometry source.
This deterministic builder adds 0.20 mm signal copper and, only where needed,
0.60/0.30 mm through vias for the fifteen audited TF SPI nets.  J4 placement
and orientation, all source copper, footprints, zones, B2, the WROOM antenna
keepout, In1.Cu, formal sources, documentation, and the UUID registry are
immutable.  The clock chain is F.Cu-only so its In1 GND reference is never
replaced by an In2-referenced detour.  Any new DRC identity or unrelated
connectivity drift fails closed.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass
import hashlib
import heapq
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

ENGINE = HARDWARE / "route_mf1750_wroom_b3_user_key_2_n_r12.py"
ENGINE_SHA256 = "b4bc903b872b997d2060a9fe681a3d76ca56774a7df43100a015ddcaae9875cf"
SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r13_r12_button_conflict_remediated.kicad_pcb"
SOURCE_SHA256 = "4cccd877a42f0e787af73183fa70548f64ac2bb00d7461cede542bc1f840d19a"

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r17_r13_tf_spi_routed.kicad_pcb"
REPORT_JSON = STAGING / "r17_r13_tf_spi_route_report.json"
SOURCE_DRC_JSON = STAGING / "r17_r13_tf_spi_source_drc.json"
CANDIDATE_DRC_JSON = STAGING / "r17_r13_tf_spi_drc.json"
BOARD_VERIFIER_JSON = STAGING / "r17_r13_tf_spi_board_verifier.json"
PREVIEW_DIR = STAGING / "r17_r13_tf_spi_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r17_r13_tf_spi_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r17_r13_tf_spi_bottom.png"
ISO_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r17_r13_tf_spi_iso.png"
FRONT_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r17_r13_tf_spi_front.svg"
BACK_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r17_r13_tf_spi_back.svg"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
ROOT_README = ROOT / "README.md"
B3_README = B3_DIR / "README.md"
STATUS_HANDOFF = ROOT / "docs" / "STATUS_HANDOFF.md"
UUID_REGISTRY = B3_DIR / "ROUTING_UUID_SEEDS.json"
UUID_REGISTRY_VERIFIER = HARDWARE / "verify_mf1750_wroom_b3_uuid_seed_registry.py"

ROUTING_UUID_SEED = 1750951
SIGNAL_WIDTH_MM = 0.20
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30
CLEARANCE_MM = 0.20
# The router lattice is 0.125 mm.  Add more than half a cell to every obstacle
# envelope so sampling/rounding can never turn a nominal 0.20 mm clearance
# into a 0.19 mm KiCad result at an arbitrary-angle segment or via.
ROUTER_SAFETY_MM = 0.075
GRID_MM = 0.125
B2_BOTTOM_MM = 60.5
ROUTE_MAX_Y_MM = 124.50
ROUTE_MIN_X_MM = 0.50
ROUTE_MAX_X_MM = 65.00
WROOM_ANTENNA_KEEPOUT = (58.75, 66.00, 79.75, 114.00)
BLOCKED = -1

ALLOWED_NETS = frozenset(
    {
        "/TF_SCLK",
        "/TF_CLK_ESD",
        "/TF_CLK_CARD",
        "/TF_MOSI",
        "/TF_CMD_ESD",
        "/TF_CMD_CARD",
        "/TF_MISO",
        "/TF_DAT0_ESD",
        "/TF_DAT0_CARD",
        "/TF_CS_N",
        "/TF_DAT3_ESD",
        "/TF_DAT3_CARD",
        "/TF_DAT1_CARD",
        "/TF_DAT2_CARD",
        "/TF_CD_N",
    }
)

# These three nets form the complete clock chain.  They may not use B.Cu or
# In2.Cu: F.Cu over the frozen In1 GND plane is the only admitted topology.
F_ONLY_NETS = frozenset({"/TF_SCLK", "/TF_CLK_ESD", "/TF_CLK_CARD"})

# Long non-clock nets leave their F.Cu SMD pads, transition through a checked
# via, and preferentially traverse B.Cu.  This preserves the F.Cu GND thermal
# spokes at U9/U10/U11 instead of building a fence around their exposed GND
# pads.  The short host-side and DAT0 ESD links remain F.Cu-preferred.
B_PREFERRED_NETS = frozenset(
    {
        "/TF_CMD_ESD",
        "/TF_CMD_CARD",
        "/TF_MISO",
        "/TF_DAT0_CARD",
        "/TF_DAT3_ESD",
        "/TF_DAT3_CARD",
        "/TF_DAT1_CARD",
        "/TF_DAT2_CARD",
        "/TF_CD_N",
    }
)

# Preserve a vertical two-spoke window through the three ESD-array GND pads.
# Signal pads lie 0.95 mm to either side and therefore remain accessible.
FRONT_GND_THERMAL_CORRIDORS = (
    (27.15, 108.45, 27.85, 111.45),  # U9.2 GND
    (31.65, 108.45, 32.35, 111.45),  # U10.2 GND
    (36.15, 108.45, 36.85, 111.45),  # U11.2 GND
)

ROUTE_ORDER = (
    "/TF_SCLK",
    "/TF_CLK_ESD",
    "/TF_CLK_CARD",
    "/TF_MOSI",
    "/TF_CMD_ESD",
    "/TF_CMD_CARD",
    "/TF_MISO",
    "/TF_DAT0_ESD",
    "/TF_DAT0_CARD",
    "/TF_CS_N",
    "/TF_DAT3_ESD",
    "/TF_DAT3_CARD",
    "/TF_DAT1_CARD",
    "/TF_DAT2_CARD",
    "/TF_CD_N",
)

EXPECTED_SOURCE_COPPER = 1364
EXPECTED_SOURCE_DRC = 13
EXPECTED_CANDIDATE_DRC = 13
EXPECTED_SOURCE_OPEN = 106
EXPECTED_CANDIDATE_OPEN = 81

EXPECTED_SOURCE_OPEN_BY_NET = {
    "/TF_SCLK": 2,
    "/TF_CLK_ESD": 1,
    "/TF_CLK_CARD": 1,
    "/TF_MOSI": 2,
    "/TF_CMD_ESD": 1,
    "/TF_CMD_CARD": 2,
    "/TF_MISO": 2,
    "/TF_DAT0_ESD": 1,
    "/TF_DAT0_CARD": 2,
    "/TF_CS_N": 2,
    "/TF_DAT3_ESD": 1,
    "/TF_DAT3_CARD": 2,
    "/TF_DAT1_CARD": 2,
    "/TF_DAT2_CARD": 2,
    "/TF_CD_N": 2,
}

# Ordered by electrical chain.  The order is also the deterministic first-pad
# anchor used by the multi-terminal router.
PAD_CONTRACT = (
    ("U1", "8", "/TF_SCLK", 48.3700, 81.2500),
    ("TP22", "1", "/TF_SCLK", 48.5000, 79.5000),
    ("R45", "1", "/TF_SCLK", 49.0000, 78.0250),
    ("R45", "2", "/TF_CLK_ESD", 49.0000, 76.3750),
    ("U9", "6", "/TF_CLK_ESD", 26.5500, 107.6625),
    ("U9", "1", "/TF_CLK_CARD", 26.5500, 109.9375),
    ("J4", "5", "/TF_CLK_CARD", 30.2050, 123.8500),
    ("U1", "9", "/TF_MOSI", 47.1000, 81.2500),
    ("TP23", "1", "/TF_MOSI", 46.5000, 79.5000),
    ("R46", "1", "/TF_MOSI", 46.0000, 78.0250),
    ("R46", "2", "/TF_CMD_ESD", 46.0000, 76.3750),
    ("U9", "4", "/TF_CMD_ESD", 28.4500, 107.6625),
    ("U9", "3", "/TF_CMD_CARD", 28.4500, 109.9375),
    ("R41", "2", "/TF_CMD_CARD", 32.8250, 101.0000),
    ("J4", "3", "/TF_CMD_CARD", 32.4050, 123.8500),
    ("U1", "10", "/TF_MISO", 45.8300, 81.2500),
    ("TP24", "1", "/TF_MISO", 45.0000, 79.5000),
    ("R47", "1", "/TF_MISO", 30.5000, 103.6750),
    ("R47", "2", "/TF_DAT0_ESD", 30.5000, 105.3250),
    ("U10", "6", "/TF_DAT0_ESD", 31.0500, 107.6625),
    ("U10", "1", "/TF_DAT0_CARD", 31.0500, 109.9375),
    ("R42", "2", "/TF_DAT0_CARD", 34.3250, 104.5000),
    ("J4", "7", "/TF_DAT0_CARD", 28.0050, 123.8500),
    ("U1", "11", "/TF_CS_N", 44.5600, 81.2500),
    ("TP25", "1", "/TF_CS_N", 43.5000, 79.5000),
    ("R48", "1", "/TF_CS_N", 43.0000, 78.0250),
    ("R48", "2", "/TF_DAT3_ESD", 43.0000, 76.3750),
    ("U10", "4", "/TF_DAT3_ESD", 32.9500, 107.6625),
    ("U10", "3", "/TF_DAT3_CARD", 32.9500, 109.9375),
    ("R40", "2", "/TF_DAT3_CARD", 36.3250, 101.0000),
    ("J4", "2", "/TF_DAT3_CARD", 33.5050, 123.8500),
    ("U11", "1", "/TF_DAT1_CARD", 35.5500, 109.9375),
    ("R43", "2", "/TF_DAT1_CARD", 39.8250, 101.0000),
    ("J4", "8", "/TF_DAT1_CARD", 26.9550, 123.8500),
    ("U11", "3", "/TF_DAT2_CARD", 37.4500, 109.9375),
    ("R39", "2", "/TF_DAT2_CARD", 37.8250, 104.5000),
    ("J4", "1", "/TF_DAT2_CARD", 34.6050, 123.8500),
    ("U1", "22", "/TF_CD_N", 39.5000, 91.9050),
    ("R44", "2", "/TF_CD_N", 41.3250, 104.5000),
    ("J4", "9", "/TF_CD_N", 37.2400, 117.7000),
)


class RouteError(RuntimeError):
    """Fail-closed TF SPI route-builder error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_engine():
    if not ENGINE.is_file() or sha256_file(ENGINE) != ENGINE_SHA256:
        raise RouteError("routing engine missing or hash-mismatched")
    spec = importlib.util.spec_from_file_location("_mf1750_r17_tf_engine", ENGINE)
    if spec is None or spec.loader is None:
        raise RouteError("could not import routing engine")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


engine = load_engine()
pcbnew = engine.pcbnew
base = engine.base


@dataclass(frozen=True)
class Node:
    x: int
    y: int
    layer: int  # 0=F.Cu, 1=B.Cu


# The two U10 signal pads first escape horizontally away from U10.2, then
# transition to B.Cu.  This is the explicit topology that prevents their two
# clearances from consuming both sides of the GND thermal.
PREFANOUTS: dict[str, tuple[Node, ...]] = {
    "/TF_DAT0_CARD": (
        Node(248, 880, 0),  # (31.000, 110.000) inside U10.1
        Node(238, 880, 0),  # (29.750, 110.000) clear of U10.2
        Node(238, 880, 1),
    ),
    "/TF_DAT3_CARD": (
        Node(264, 880, 0),  # (33.000, 110.000) inside U10.3
        Node(274, 880, 0),  # (34.250, 110.000) clear of U10.2
        Node(274, 880, 1),
    ),
}

# J4.8 otherwise remains on F.Cu for roughly 14 mm before the search can find
# a late via, and that long front segment partitions the GND fill.  Escape the
# pad toward the connector interior, change layer once, then let A* connect the
# B.Cu endpoint to the already-routed DAT1 component.
BRANCH_PREFANOUTS: dict[tuple[str, str, str], tuple[Node, ...]] = {
    ("/TF_DAT1_CARD", "J4", "8"): (
        Node(216, 991, 0),  # (27.000, 123.875) inside J4.8
        Node(215, 976, 0),  # (26.875, 122.000), clear of DAT0 card escape
        Node(215, 976, 1),
    ),
}


def mm_to_grid(value: float) -> int:
    return int(round(value / GRID_MM))


def grid_to_mm(value: int) -> float:
    return value * GRID_MM


def node_point(node: Node):
    return pcbnew.VECTOR2I(
        pcbnew.FromMM(grid_to_mm(node.x)), pcbnew.FromMM(grid_to_mm(node.y))
    )


def point_in_rect(point: tuple[float, float], rect: tuple[float, float, float, float]) -> bool:
    x_value, y_value = point
    x0, y0, x1, y1 = rect
    return x0 <= x_value <= x1 and y0 <= y_value <= y1


def segment_hits_rect(
    start: tuple[float, float], end: tuple[float, float], rect: tuple[float, float, float, float]
) -> bool:
    x0, y0, x1, y1 = rect
    xa, ya = start
    xb, yb = end
    dx, dy = xb - xa, yb - ya
    lo, hi = 0.0, 1.0
    for p_value, q_value in zip(
        (-dx, dx, -dy, dy),
        (xa - x0, x1 - xa, ya - y0, y1 - ya),
        strict=True,
    ):
        if abs(p_value) < 1e-12:
            if q_value < 0:
                return False
            continue
        ratio = q_value / p_value
        if p_value < 0:
            lo = max(lo, ratio)
        else:
            hi = min(hi, ratio)
        if lo > hi:
            return False
    return True


def merge_owner(owners: dict[tuple[int, int], int], cell: tuple[int, int], owner: int) -> None:
    previous = owners.get(cell)
    if previous is None or previous == owner:
        owners[cell] = owner
    else:
        owners[cell] = BLOCKED


class GridRouter:
    """Small deterministic router for the fixed lower-board TF region.

    It treats every source pad/track/via as immutable geometry, uses an exact
    0.125 mm search lattice, and asks KiCad DRC to authoritatively validate the
    resulting candidate.  B.Cu has a mild traversal penalty and layer changes
    have a strong penalty, producing F.Cu-first routes without inventing an
    In1 signal layer.
    """

    def __init__(self, board) -> None:
        self.board = board
        self.layer_ids = (pcbnew.F_Cu, pcbnew.B_Cu)
        self.owners: list[dict[tuple[int, int], int]] = [dict(), dict()]
        self.via_owners: dict[tuple[int, int], int] = {}
        self.net_nodes: dict[int, set[Node]] = collections.defaultdict(set)
        self.track_count = 0
        self.via_count = 0
        self.layer_track_counts: collections.Counter[str] = collections.Counter()
        self.net_object_counts: collections.Counter[str] = collections.Counter()
        self.net_lengths_mm: collections.Counter[str] = collections.Counter()
        self._mark_source_geometry()

    def _inside(self, node: Node) -> bool:
        x_mm = grid_to_mm(node.x)
        y_mm = grid_to_mm(node.y)
        if not (
            ROUTE_MIN_X_MM <= x_mm <= ROUTE_MAX_X_MM
            and B2_BOTTOM_MM <= y_mm <= ROUTE_MAX_Y_MM
        ):
            return False
        return not point_in_rect((x_mm, y_mm), WROOM_ANTENNA_KEEPOUT)

    def _mark_disk(
        self,
        owners: dict[tuple[int, int], int],
        x_mm: float,
        y_mm: float,
        radius_mm: float,
        owner: int,
    ) -> None:
        center_x = mm_to_grid(x_mm)
        center_y = mm_to_grid(y_mm)
        radius = int(math.ceil(radius_mm / GRID_MM))
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if math.hypot(dx * GRID_MM, dy * GRID_MM) <= radius_mm + 1e-9:
                    merge_owner(owners, (center_x + dx, center_y + dy), owner)

    def _mark_box(
        self,
        owners: dict[tuple[int, int], int],
        left_mm: float,
        top_mm: float,
        right_mm: float,
        bottom_mm: float,
        owner: int,
    ) -> None:
        for gx in range(math.floor(left_mm / GRID_MM), math.ceil(right_mm / GRID_MM) + 1):
            x_mm = grid_to_mm(gx)
            if not left_mm <= x_mm <= right_mm:
                continue
            for gy in range(math.floor(top_mm / GRID_MM), math.ceil(bottom_mm / GRID_MM) + 1):
                y_mm = grid_to_mm(gy)
                if top_mm <= y_mm <= bottom_mm:
                    merge_owner(owners, (gx, gy), owner)

    def _mark_segment(
        self,
        owners: dict[tuple[int, int], int],
        start: tuple[float, float],
        end: tuple[float, float],
        radius_mm: float,
        owner: int,
    ) -> None:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        samples = max(1, int(math.ceil(math.hypot(dx, dy) / (GRID_MM / 2))))
        for index in range(samples + 1):
            ratio = index / samples
            self._mark_disk(
                owners,
                start[0] + dx * ratio,
                start[1] + dy * ratio,
                radius_mm,
                owner,
            )

    def _pad_layers(self, pad) -> tuple[int, ...]:
        return tuple(
            index for index, layer_id in enumerate(self.layer_ids) if pad.IsOnLayer(layer_id)
        )

    def _mark_source_geometry(self) -> None:
        target_codes = {
            self.board.GetNetcodeFromNetname(net_name): net_name for net_name in ALLOWED_NETS
        }
        trace_margin = CLEARANCE_MM + SIGNAL_WIDTH_MM / 2 + ROUTER_SAFETY_MM
        via_margin = CLEARANCE_MM + VIA_DIAMETER_MM / 2 + ROUTER_SAFETY_MM

        for footprint in self.board.GetFootprints():
            for pad in footprint.Pads():
                bbox = pad.GetBoundingBox()
                left = pcbnew.ToMM(bbox.GetLeft())
                right = pcbnew.ToMM(bbox.GetRight())
                top = pcbnew.ToMM(bbox.GetTop())
                bottom = pcbnew.ToMM(bbox.GetBottom())
                owner = pad.GetNetCode() if pad.GetNetCode() in target_codes else BLOCKED
                for layer in self._pad_layers(pad):
                    self._mark_box(
                        self.owners[layer],
                        left - trace_margin,
                        top - trace_margin,
                        right + trace_margin,
                        bottom + trace_margin,
                        owner,
                    )
                # A new through via must clear every copper-bearing pad layer.
                if any(pad.IsOnLayer(layer) for layer in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)):
                    self._mark_box(
                        self.via_owners,
                        left - via_margin,
                        top - via_margin,
                        right + via_margin,
                        bottom + via_margin,
                        owner,
                    )

        for item in self.board.GetTracks():
            owner = item.GetNetCode() if item.GetNetCode() in target_codes else BLOCKED
            if isinstance(item, pcbnew.PCB_VIA):
                position = base.point_mm(item.GetPosition())
                source_radius = pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)) / 2
                for layer in range(2):
                    self._mark_disk(
                        self.owners[layer],
                        position[0],
                        position[1],
                        source_radius + trace_margin,
                        owner,
                    )
                self._mark_disk(
                    self.via_owners,
                    position[0],
                    position[1],
                        source_radius + CLEARANCE_MM + VIA_DIAMETER_MM / 2 + ROUTER_SAFETY_MM,
                    owner,
                )
                continue

            start = base.point_mm(item.GetStart())
            end = base.point_mm(item.GetEnd())
            source_radius = pcbnew.ToMM(item.GetWidth()) / 2
            if item.GetLayer() in self.layer_ids:
                layer = self.layer_ids.index(item.GetLayer())
                self._mark_segment(
                    self.owners[layer],
                    start,
                    end,
                    source_radius + trace_margin,
                    owner,
                )
            # A new through via must also clear immutable In2 tracks.
            self._mark_segment(
                self.via_owners,
                start,
                end,
                source_radius + CLEARANCE_MM + VIA_DIAMETER_MM / 2 + ROUTER_SAFETY_MM,
                owner,
            )

        for left, top, right, bottom in FRONT_GND_THERMAL_CORRIDORS:
            self._mark_box(self.owners[0], left, top, right, bottom, BLOCKED)
            self._mark_box(self.via_owners, left, top, right, bottom, BLOCKED)

    def _cell_allowed(self, node: Node, netcode: int) -> bool:
        if not self._inside(node):
            return False
        owner = self.owners[node.layer].get((node.x, node.y))
        return owner is None or owner == netcode

    def _via_allowed(self, node: Node, netcode: int) -> bool:
        if not self._inside(node):
            return False
        owner = self.via_owners.get((node.x, node.y))
        return owner is None or owner == netcode

    @staticmethod
    def _heuristic(node: Node, targets: set[Node], via_cost: float) -> float:
        return min(
            math.hypot(node.x - target.x, node.y - target.y)
            + (via_cost if node.layer != target.layer else 0.0)
            for target in targets
        )

    def _pad_node(self, pad) -> Node:
        position = pad.GetPosition()
        return Node(
            mm_to_grid(pcbnew.ToMM(position.x)),
            mm_to_grid(pcbnew.ToMM(position.y)),
            0,
        )

    def find_path(
        self,
        start: Node,
        targets: set[Node],
        netcode: int,
        *,
        force_front: bool,
        prefer_back: bool,
    ) -> list[Node] | None:
        if not self._cell_allowed(start, netcode):
            return None
        targets = {target for target in targets if self._cell_allowed(target, netcode)}
        if not targets:
            return None
        queue: list[tuple[float, int, Node]] = []
        serial = 0
        g_score = {start: 0.0}
        previous: dict[Node, Node] = {}
        via_cost = 20.0 if prefer_back else 80.0
        heapq.heappush(queue, (self._heuristic(start, targets, via_cost), serial, start))
        visited: set[Node] = set()
        moves = (
            (0, 1, 1.0),
            (-1, 0, 1.0),
            (1, 0, 1.0),
            (0, -1, 1.0),
            (-1, 1, math.sqrt(2)),
            (1, 1, math.sqrt(2)),
            (-1, -1, math.sqrt(2)),
            (1, -1, math.sqrt(2)),
        )
        while queue:
            _estimate, _serial, current = heapq.heappop(queue)
            if current in visited:
                continue
            visited.add(current)
            if current in targets:
                path = [current]
                while path[-1] != start:
                    path.append(previous[path[-1]])
                path.reverse()
                return path
            for dx, dy, distance in moves:
                nxt = Node(current.x + dx, current.y + dy, current.layer)
                if not self._cell_allowed(nxt, netcode):
                    continue
                if dx and dy:
                    if not self._cell_allowed(Node(current.x + dx, current.y, current.layer), netcode):
                        continue
                    if not self._cell_allowed(Node(current.x, current.y + dy, current.layer), netcode):
                        continue
                if prefer_back:
                    layer_factor = 1.25 if nxt.layer == 0 else 1.0
                else:
                    layer_factor = 1.0 if nxt.layer == 0 else 1.10
                tentative = g_score[current] + distance * layer_factor
                if tentative < g_score.get(nxt, math.inf):
                    previous[nxt] = current
                    g_score[nxt] = tentative
                    serial += 1
                    heapq.heappush(
                        queue,
                        (tentative + self._heuristic(nxt, targets, via_cost), serial, nxt),
                    )
            if not force_front:
                other = Node(current.x, current.y, 1 - current.layer)
                if self._cell_allowed(other, netcode) and self._via_allowed(current, netcode):
                    tentative = g_score[current] + via_cost
                    if tentative < g_score.get(other, math.inf):
                        previous[other] = current
                        g_score[other] = tentative
                        serial += 1
                        heapq.heappush(
                            queue,
                            (tentative + self._heuristic(other, targets, via_cost), serial, other),
                        )
        return None

    def _direct_clear(self, start: Node, end: Node, netcode: int) -> bool:
        if start.layer != end.layer:
            return False
        dx = end.x - start.x
        dy = end.y - start.y
        samples = max(1, int(math.ceil(math.hypot(dx, dy) * 2)))
        for index in range(samples + 1):
            ratio = index / samples
            node = Node(
                round(start.x + dx * ratio),
                round(start.y + dy * ratio),
                start.layer,
            )
            if not self._cell_allowed(node, netcode):
                return False
        return True

    def simplify_path(self, path: list[Node], netcode: int) -> list[Node]:
        """Greedily collapse A* stair-steps into verified straight segments."""
        if len(path) < 3:
            return path
        result = [path[0]]
        index = 0
        while index < len(path) - 1:
            # A via transition is an explicit adjacent pair at one coordinate.
            if path[index + 1].layer != path[index].layer:
                result.append(path[index + 1])
                index += 1
                continue
            farthest = index + 1
            probe = farthest + 1
            while probe < len(path) and path[probe].layer == path[index].layer:
                if self._direct_clear(path[index], path[probe], netcode):
                    farthest = probe
                probe += 1
            result.append(path[farthest])
            index = farthest
        return result

    def _mark_new_track(self, a: Node, b: Node, netcode: int) -> None:
        start = (grid_to_mm(a.x), grid_to_mm(a.y))
        end = (grid_to_mm(b.x), grid_to_mm(b.y))
        self._mark_segment(
            self.owners[a.layer],
            start,
            end,
            SIGNAL_WIDTH_MM / 2
            + CLEARANCE_MM
            + SIGNAL_WIDTH_MM / 2
            + ROUTER_SAFETY_MM,
            netcode,
        )
        self._mark_segment(
            self.via_owners,
            start,
            end,
            SIGNAL_WIDTH_MM / 2
            + CLEARANCE_MM
            + VIA_DIAMETER_MM / 2
            + ROUTER_SAFETY_MM,
            netcode,
        )

    def _mark_new_via(self, node: Node, netcode: int) -> None:
        point = (grid_to_mm(node.x), grid_to_mm(node.y))
        for layer in range(2):
            self._mark_disk(
                self.owners[layer],
                point[0],
                point[1],
                VIA_DIAMETER_MM / 2
                + CLEARANCE_MM
                + SIGNAL_WIDTH_MM / 2
                + ROUTER_SAFETY_MM,
                netcode,
            )
        self._mark_disk(
            self.via_owners,
            point[0],
            point[1],
            VIA_DIAMETER_MM + CLEARANCE_MM + ROUTER_SAFETY_MM,
            netcode,
        )

    def commit_path(
        self,
        path: list[Node],
        net_name: str,
        added_ids: list[str],
        *,
        register_nodes: bool = True,
    ) -> None:
        if len(path) < 2:
            return
        netcode = self.board.GetNetcodeFromNetname(net_name)
        segment_start = path[0]
        last = path[0]
        direction: tuple[int, int, int] | None = None

        def add_segment(start: Node, end: Node) -> None:
            if start == end:
                return
            if start.layer != end.layer:
                raise RouteError("attempted cross-layer PCB_TRACK")
            layer_name = "F.Cu" if start.layer == 0 else "B.Cu"
            item = base.add_track(
                self.board,
                net_name,
                layer_name,
                SIGNAL_WIDTH_MM,
                (grid_to_mm(start.x), grid_to_mm(start.y)),
                (grid_to_mm(end.x), grid_to_mm(end.y)),
            )
            added_ids.append(base.item_uuid(item))
            self.track_count += 1
            self.layer_track_counts[layer_name] += 1
            self.net_object_counts[net_name] += 1
            self.net_lengths_mm[net_name] += math.hypot(end.x - start.x, end.y - start.y) * GRID_MM
            self._mark_new_track(start, end, netcode)

        for current in path[1:]:
            if current.layer != last.layer:
                add_segment(segment_start, last)
                item = base.add_via(
                    self.board,
                    net_name,
                    grid_to_mm(last.x),
                    grid_to_mm(last.y),
                )
                added_ids.append(base.item_uuid(item))
                self.via_count += 1
                self.net_object_counts[net_name] += 1
                self._mark_new_via(last, netcode)
                segment_start = current
                direction = None
            else:
                step = (current.x - last.x, current.y - last.y, current.layer)
                if direction is None:
                    direction = step
                elif step != direction:
                    add_segment(segment_start, last)
                    segment_start = last
                    direction = step
            last = current
        add_segment(segment_start, last)
        if register_nodes:
            self.net_nodes[netcode].update(path)

    def route_net(self, net_name: str, pads: list[object], added_ids: list[str]) -> None:
        if len(pads) < 2:
            raise RouteError(f"net has fewer than two pads: {net_name}")
        netcode = pads[0].GetNetCode()
        if any(pad.GetNetCode() != netcode for pad in pads):
            raise RouteError(f"pad netcode mismatch: {net_name}")
        root = self._pad_node(pads[0])
        connected = [pads[0]]
        if net_name in PREFANOUTS:
            if not self.net_nodes[netcode]:
                raise RouteError(f"prefanout was not seeded before branch routing: {net_name}")
        else:
            self.net_nodes[netcode].add(root)
        remaining = list(pads[1:])
        branch_starts: dict[tuple[str, str], Node] = {}
        branch_nodes: dict[tuple[str, str], set[Node]] = {}
        for pad in remaining:
            reference = pad.GetParentFootprint().GetReference()
            key = (net_name, reference, pad.GetNumber())
            if key not in BRANCH_PREFANOUTS:
                continue
            branch = list(BRANCH_PREFANOUTS[key])
            pad_root = self._pad_node(pad)
            if branch[0] != pad_root:
                raise RouteError(f"branch prefanout root drift for {key}: {branch[0]} != {pad_root}")
            for first, second in zip(branch, branch[1:], strict=False):
                if first.layer == second.layer:
                    if not self._direct_clear(first, second, netcode):
                        raise RouteError(f"branch prefanout track blocked for {key}: {first}->{second}")
                elif (
                    first.x != second.x
                    or first.y != second.y
                    or not self._via_allowed(first, netcode)
                    or not self._cell_allowed(second, netcode)
                ):
                    raise RouteError(f"branch prefanout via blocked for {key}: {first}->{second}")
            self.commit_path(branch, net_name, added_ids, register_nodes=False)
            branch_key = (reference, pad.GetNumber())
            branch_starts[branch_key] = branch[-1]
            branch_nodes[branch_key] = set(branch)
        while remaining:
            best: tuple[int, int, object] | None = None
            for index, pad in enumerate(remaining):
                position = pad.GetPosition()
                metric = min(
                    (position.x - other.GetPosition().x) ** 2
                    + (position.y - other.GetPosition().y) ** 2
                    for other in connected
                )
                candidate = (metric, index, pad)
                if best is None or candidate[:2] < best[:2]:
                    best = candidate
            assert best is not None
            _metric, index, pad = best
            branch_key = (pad.GetParentFootprint().GetReference(), pad.GetNumber())
            start = branch_starts.get(branch_key, self._pad_node(pad))
            targets = set(self.net_nodes[netcode])
            path = self.find_path(
                start,
                targets,
                netcode,
                force_front=net_name in F_ONLY_NETS,
                prefer_back=net_name in B_PREFERRED_NETS,
            )
            if path is None:
                reference = pad.GetParentFootprint().GetReference()
                raise RouteError(
                    f"no legal path for {net_name} from {reference}.{pad.GetNumber()} "
                    f"at {(grid_to_mm(start.x), grid_to_mm(start.y))}; "
                    f"force_front={net_name in F_ONLY_NETS}"
                )
            path = self.simplify_path(path, netcode)
            self.commit_path(path, net_name, added_ids)
            self.net_nodes[netcode].update(branch_nodes.get(branch_key, set()))
            connected.append(pad)
            remaining.pop(index)

    def seed_prefanout(self, net_name: str, pad: object, added_ids: list[str]) -> None:
        netcode = pad.GetNetCode()
        root = self._pad_node(pad)
        prefanout = list(PREFANOUTS[net_name])
        if prefanout[0] != root:
            raise RouteError(f"prefanout root drift for {net_name}: {prefanout[0]} != {root}")
        for first, second in zip(prefanout, prefanout[1:], strict=False):
            if first.layer == second.layer:
                if not self._direct_clear(first, second, netcode):
                    blockers = []
                    for gx in range(min(first.x, second.x), max(first.x, second.x) + 1):
                        owner = self.owners[first.layer].get((gx, first.y))
                        if owner is not None and owner != netcode:
                            blockers.append(
                                {
                                    "at_mm": [grid_to_mm(gx), grid_to_mm(first.y)],
                                    "owner_netcode": owner,
                                }
                            )
                    raise RouteError(
                        f"prefanout track blocked for {net_name}: {first}->{second}; "
                        + json.dumps(blockers)
                    )
            elif (
                first.x != second.x
                or first.y != second.y
                or not self._via_allowed(first, netcode)
                or not self._cell_allowed(second, netcode)
            ):
                raise RouteError(f"prefanout via blocked for {net_name}: {first}->{second}")
        self.commit_path(prefanout, net_name, added_ids)

    def summary(self) -> dict[str, object]:
        return {
            "algorithm": "deterministic_0p125_mm_A_star_source_geometry_obstacle_map",
            "signal_width_mm": SIGNAL_WIDTH_MM,
            "via_mm": [VIA_DIAMETER_MM, VIA_DRILL_MM],
            "clearance_model_mm": CLEARANCE_MM,
            "router_safety_mm": ROUTER_SAFETY_MM,
            "track_count": self.track_count,
            "via_count": self.via_count,
            "layer_track_counts": dict(sorted(self.layer_track_counts.items())),
            "net_object_counts": dict(sorted(self.net_object_counts.items())),
            "net_lengths_mm": {
                net: round(length, 4) for net, length in sorted(self.net_lengths_mm.items())
            },
            "f_only_nets": sorted(F_ONLY_NETS),
            "b_preferred_nets": sorted(B_PREFERRED_NETS),
            "front_gnd_thermal_corridors_mm": [list(rect) for rect in FRONT_GND_THERMAL_CORRIDORS],
            "explicit_prefanout_nets": sorted(PREFANOUTS),
            "explicit_branch_prefanouts": [list(key) for key in sorted(BRANCH_PREFANOUTS)],
            "route_order": list(ROUTE_ORDER),
        }


LAST_ROUTE_SUMMARY: dict[str, object] = {}


def pad_lookup(board) -> dict[str, list[object]]:
    by_net: dict[str, list[object]] = collections.defaultdict(list)
    for reference, number, net_name, x_mm, y_mm in PAD_CONTRACT:
        footprint = board.FindFootprintByReference(reference)
        if footprint is None:
            raise RouteError(f"missing footprint {reference}")
        matches = [
            pad
            for pad in footprint.Pads()
            if pad.GetNumber() == number
            and base.point_mm(pad.GetPosition()) == (x_mm, y_mm)
            and pad.GetNetname() == net_name
        ]
        if len(matches) != 1:
            raise RouteError(f"pad contract drift: {reference}.{number} {net_name}@{(x_mm, y_mm)}")
        by_net[net_name].append(matches[0])
    return by_net


def validate_source(board, before) -> dict[str, object]:
    by_net = pad_lookup(board)
    source_counts = collections.Counter(signature[1] for signature in before["tracks"].values())
    j4 = board.FindFootprintByReference("J4")
    if j4 is None:
        raise RouteError("J4 missing")
    j4_position = base.point_mm(j4.GetPosition())
    j4_rotation = round(float(j4.GetOrientationDegrees()), 6)
    checks = {
        "source_copper_count_1364": len(before["tracks"]) == EXPECTED_SOURCE_COPPER,
        "source_copper_uuid_unique": before["copper_uuid_audit"]["passed"] is True,
        "source_has_no_tf_spi_copper": all(source_counts.get(net, 0) == 0 for net in ALLOWED_NETS),
        "pad_contract_exact_40": sum(len(pads) for pads in by_net.values()) == len(PAD_CONTRACT) == 40,
        "target_net_set_exact_15": set(by_net) == set(ALLOWED_NETS),
        "j4_position_frozen": j4_position == (31.5, 118.4),
        "j4_rotation_frozen": j4_rotation == 180.0,
        "j4_front_side_frozen": j4.GetLayer() == pcbnew.F_Cu,
    }
    if not all(checks.values()):
        raise RouteError("source contract failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "j4": {"position_mm": list(j4_position), "rotation_deg": j4_rotation, "layer": "F.Cu"},
        "pad_count_by_net": {net: len(pads) for net, pads in sorted(by_net.items())},
        "pads": [
            {
                "reference": reference,
                "pad": number,
                "net": net_name,
                "position_mm": [x_mm, y_mm],
            }
            for reference, number, net_name, x_mm, y_mm in PAD_CONTRACT
        ],
    }


def add_routes(board) -> set[str]:
    global LAST_ROUTE_SUMMARY
    pcbnew.KIID.SeedGenerator(ROUTING_UUID_SEED)
    by_net = pad_lookup(board)
    router = GridRouter(board)
    added_ids: list[str] = []
    # Reserve both sides of U10.2 before either multi-terminal net can occupy
    # the other side's escape corridor.
    for net_name in sorted(PREFANOUTS):
        router.seed_prefanout(net_name, by_net[net_name][0], added_ids)
    for net_name in ROUTE_ORDER:
        router.route_net(net_name, by_net[net_name], added_ids)
    if len(set(added_ids)) != len(added_ids):
        raise RouteError("new deterministic copper UUID collision")
    LAST_ROUTE_SUMMARY = router.summary()
    LAST_ROUTE_SUMMARY["added_uuid_count"] = len(added_ids)
    return set(added_ids)


def preservation_and_envelope_audit(candidate, before, added_ids) -> dict[str, object]:
    after = base.source_state(candidate)
    source_ids = set(before["tracks"])
    candidate_ids = set(after["tracks"])
    extra_ids = candidate_ids - source_ids
    missing_source = sorted(source_ids - candidate_ids)
    changed_source = sorted(
        item_id
        for item_id in source_ids & candidate_ids
        if before["tracks"][item_id] != after["tracks"][item_id]
    )
    unexpected_extra = sorted(extra_ids - added_ids)
    missing_added = sorted(added_ids - extra_ids)
    objects = {base.item_uuid(item): item for item in candidate.GetTracks()}
    findings = {
        "bad_net": [],
        "bad_width": [],
        "bad_via": [],
        "b2": [],
        "antenna": [],
        "in1": [],
        "in2": [],
        "clock_not_front": [],
    }
    for item_id in sorted(extra_ids):
        item = objects[item_id]
        net_name = item.GetNetname()
        if net_name not in ALLOWED_NETS:
            findings["bad_net"].append(item_id)
        if isinstance(item, pcbnew.PCB_VIA):
            points = [base.point_mm(item.GetPosition())]
            if (
                round(pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)), 6),
                round(pcbnew.ToMM(item.GetDrillValue()), 6),
            ) != (VIA_DIAMETER_MM, VIA_DRILL_MM):
                findings["bad_via"].append(item_id)
            antenna_hit = point_in_rect(points[0], WROOM_ANTENNA_KEEPOUT)
            if net_name in F_ONLY_NETS:
                findings["clock_not_front"].append(item_id)
        else:
            points = [base.point_mm(item.GetStart()), base.point_mm(item.GetEnd())]
            if round(pcbnew.ToMM(item.GetWidth()), 6) != SIGNAL_WIDTH_MM:
                findings["bad_width"].append(item_id)
            layer_name = candidate.GetLayerName(item.GetLayer())
            if layer_name == "In1.Cu":
                findings["in1"].append(item_id)
            if layer_name == "In2.Cu":
                findings["in2"].append(item_id)
            if net_name in F_ONLY_NETS and layer_name != "F.Cu":
                findings["clock_not_front"].append(item_id)
            antenna_hit = segment_hits_rect(points[0], points[1], WROOM_ANTENNA_KEEPOUT)
        if any(y_value < B2_BOTTOM_MM for _, y_value in points):
            findings["b2"].append(item_id)
        if antenna_hit:
            findings["antenna"].append(item_id)
    new_counts = collections.Counter(after["tracks"][item_id][1] for item_id in extra_ids)
    added_track_count = sum(not isinstance(objects[item_id], pcbnew.PCB_VIA) for item_id in extra_ids)
    added_via_count = sum(isinstance(objects[item_id], pcbnew.PCB_VIA) for item_id in extra_ids)
    j4_before = before["footprints"]
    checks = {
        "all_source_copper_uuid_geometry_exact": not missing_source and not changed_source,
        "only_deterministic_added_ids": not unexpected_extra and not missing_added,
        "new_uuid_intersection_with_source_zero": not (added_ids & source_ids),
        "candidate_copper_uuid_unique": after["copper_uuid_audit"]["passed"] is True,
        "candidate_copper_count_is_source_plus_added": len(after["tracks"]) == EXPECTED_SOURCE_COPPER + len(added_ids),
        "added_track_count_matches_router": added_track_count == LAST_ROUTE_SUMMARY.get("track_count"),
        "added_via_count_matches_router": added_via_count == LAST_ROUTE_SUMMARY.get("via_count"),
        "new_copper_exact_target_net_set": set(new_counts) == set(ALLOWED_NETS),
        "every_target_net_has_new_copper": all(new_counts.get(net, 0) > 0 for net in ALLOWED_NETS),
        "footprints_exact": j4_before == after["footprints"],
        "zones_exact": before["zones"] == after["zones"],
        "no_new_copper_in_b2": not findings["b2"],
        "no_new_copper_in_antenna_keepout": not findings["antenna"],
        "no_new_signal_track_on_in1": not findings["in1"],
        "no_new_signal_track_on_in2": not findings["in2"],
        "clock_chain_front_only": not findings["clock_not_front"],
        "all_new_tracks_0p20_mm": not findings["bad_width"],
        "all_new_vias_0p60_0p30_mm": not findings["bad_via"],
        "no_bad_new_net": not findings["bad_net"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "source_copper_count": len(before["tracks"]),
        "candidate_copper_count": len(after["tracks"]),
        "added_track_count": added_track_count,
        "added_via_count": added_via_count,
        "added_ids": sorted(extra_ids),
        "removed_ids": missing_source,
        "changed_source_ids": changed_source,
        "unexpected_extra": unexpected_extra,
        "missing_added": missing_added,
        "new_net_counts": dict(sorted(new_counts.items())),
        "envelope_findings": findings,
        "routing_summary": LAST_ROUTE_SUMMARY,
    }


def unconnected_by_net(raw) -> dict[str, int]:
    counts: collections.Counter[str] = collections.Counter()
    for entry in raw.get("unconnected_items", []):
        names = []
        for item in entry.get("items", []):
            names.extend(re.findall(r"\[([^\]]+)\]", str(item.get("description", ""))))
        unique = set(name for name in names if name)
        counts[next(iter(unique)) if len(unique) == 1 else "<MIXED_OR_EMPTY>"] += 1
    return dict(sorted(counts.items()))


def violation_identity(raw) -> list[tuple[str, tuple[str, ...], tuple[tuple[float, float], ...]]]:
    return sorted(
        (
            str(violation.get("type", "")),
            tuple(sorted(str(item.get("uuid", "")) for item in violation.get("items", []))),
            tuple(
                sorted(
                    (
                        round(float(item.get("pos", {}).get("x", 0.0)), 6),
                        round(float(item.get("pos", {}).get("y", 0.0)), 6),
                    )
                    for item in violation.get("items", [])
                )
            ),
        )
        for violation in raw.get("violations", [])
    )


def drc_gate(source, candidate) -> dict[str, object]:
    source_nets = unconnected_by_net(source["raw"])
    candidate_nets = unconnected_by_net(candidate["raw"])
    other_nets = (set(source_nets) | set(candidate_nets)) - ALLOWED_NETS
    other_drift = {
        net: {"source": source_nets.get(net, 0), "candidate": candidate_nets.get(net, 0)}
        for net in sorted(other_nets)
        if source_nets.get(net, 0) != candidate_nets.get(net, 0)
    }
    source_target = {net: source_nets.get(net, 0) for net in sorted(ALLOWED_NETS)}
    candidate_target = {net: candidate_nets.get(net, 0) for net in sorted(ALLOWED_NETS)}
    checks = {
        "source_violation_count_13": source["violation_count"] == EXPECTED_SOURCE_DRC,
        "candidate_violation_count_13": candidate["violation_count"] == EXPECTED_CANDIDATE_DRC,
        "inherited_violation_uuid_position_identity_exact": violation_identity(source["raw"])
        == violation_identity(candidate["raw"]),
        "source_open_106": source["unconnected_count"] == EXPECTED_SOURCE_OPEN,
        "candidate_open_81": candidate["unconnected_count"] == EXPECTED_CANDIDATE_OPEN,
        "exact_open_reduction_25": source["unconnected_count"] - candidate["unconnected_count"] == 25,
        "source_target_open_map_exact": source_target == EXPECTED_SOURCE_OPEN_BY_NET,
        "candidate_every_tf_spi_net_open_zero": all(value == 0 for value in candidate_target.values()),
        "dcdc_en_remains_0": candidate_nets.get("/DCDC_EN", 0) == 0,
        "boot_n_remains_0": candidate_nets.get("/BOOT_N", 0) == 0,
        "ps_hold_remains_0": candidate_nets.get("/PS_HOLD", 0) == 0,
        "pwr_button_n_remains_0": candidate_nets.get("/PWR_BUTTON_N", 0) == 0,
        "user_key_1_n_remains_0": candidate_nets.get("/USER_KEY_1_N", 0) == 0,
        "user_key_2_n_remains_0": candidate_nets.get("/USER_KEY_2_N", 0) == 0,
        "all_other_net_open_counts_unchanged": not other_drift,
        "schematic_parity_zero": candidate["schematic_parity_count"] == 0,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "source_unconnected_by_net": source_nets,
        "candidate_unconnected_by_net": candidate_nets,
        "source_target_open_map": source_target,
        "candidate_target_open_map": candidate_target,
        "other_net_drift": other_drift,
        "source_violation_identity": violation_identity(source["raw"]),
        "candidate_violation_identity": violation_identity(candidate["raw"]),
    }


def protected_hashes() -> dict[str, str | None]:
    paths = (
        SOURCE_BOARD,
        ENGINE,
        FORMAL_BOARD,
        FORMAL_SCHEMATIC,
        FORMAL_PROJECT,
        ROOT_README,
        B3_README,
        STATUS_HANDOFF,
        UUID_REGISTRY,
    )
    return {str(path.resolve()): sha256_file(path) if path.is_file() else None for path in paths}


def render_isometric(kicad_cli: Path) -> dict[str, object]:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mf1750-r17-tf-iso-") as name:
        temporary = Path(name)
        outputs = [temporary / "iso1.png", temporary / "iso2.png"]
        hashes = []
        commands = []
        for output in outputs:
            command = [
                str(kicad_cli),
                "pcb",
                "render",
                "--side",
                "top",
                "--background",
                "opaque",
                "--quality",
                "high",
                "--width",
                "1800",
                "--height",
                "1600",
                "--perspective",
                "--floor",
                "--rotate",
                "315,0,45",
                "--output",
                str(output),
                str(OUTPUT_BOARD),
            ]
            completed = subprocess.run(
                command,
                cwd=ROOT,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
            )
            if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
                raise RouteError(
                    "isometric render failed: "
                    + (completed.stderr.strip() or completed.stdout.strip())
                )
            hashes.append(sha256_file(output))
            commands.append(command)
        os.replace(outputs[0], ISO_PREVIEW)
    return {
        "path": str(ISO_PREVIEW),
        "bytes": ISO_PREVIEW.stat().st_size,
        "sha256": sha256_file(ISO_PREVIEW),
        "repeat_hashes": hashes,
        "byte_identical": hashes[0] == hashes[1],
        "classification": "VISUAL_EVIDENCE_ONLY_NOT_A_PCB_DETERMINISM_GATE",
        "commands": commands,
    }


def configure_engine() -> None:
    engine.SOURCE_BOARD = SOURCE_BOARD
    engine.SOURCE_SHA256 = SOURCE_SHA256
    engine.OUTPUT_BOARD = OUTPUT_BOARD
    engine.REPORT_JSON = REPORT_JSON
    engine.SOURCE_DRC_JSON = SOURCE_DRC_JSON
    engine.CANDIDATE_DRC_JSON = CANDIDATE_DRC_JSON
    engine.BOARD_VERIFIER_JSON = BOARD_VERIFIER_JSON
    engine.PREVIEW_DIR = PREVIEW_DIR
    engine.TOP_PREVIEW = TOP_PREVIEW
    engine.BOTTOM_PREVIEW = BOTTOM_PREVIEW
    engine.FRONT_COPPER_SVG = FRONT_COPPER_SVG
    engine.BACK_COPPER_SVG = BACK_COPPER_SVG
    engine.ROUTING_UUID_SEED = ROUTING_UUID_SEED
    engine.ALLOWED_NET = "/TF_SPI_BUNDLE_WRAPPER"
    engine.ALLOWED_NETS = ALLOWED_NETS
    engine.ROUTES = ()
    engine.VIAS = ()
    engine.EXPECTED_SOURCE_COPPER = EXPECTED_SOURCE_COPPER
    engine.EXPECTED_SOURCE_DRC = EXPECTED_SOURCE_DRC
    engine.EXPECTED_CANDIDATE_DRC = EXPECTED_CANDIDATE_DRC
    engine.EXPECTED_SOURCE_OPEN = EXPECTED_SOURCE_OPEN
    engine.EXPECTED_CANDIDATE_OPEN = EXPECTED_CANDIDATE_OPEN
    engine.PAD_CONTRACT = PAD_CONTRACT
    engine.validate_source = validate_source
    engine.add_routes = add_routes
    engine.preservation_and_envelope_audit = preservation_and_envelope_audit
    engine.drc_gate = drc_gate
    engine.protected_hashes = protected_hashes


def rewrite_report(exit_code: int) -> None:
    if not REPORT_JSON.is_file():
        return
    report = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    passed = report.get("routing_checks_passed") is True and exit_code == 0
    report["operating_mode"] = "REVISION"
    report["mode"] = "STAGING_ONLY_TF_SPI_15_NET_ROUTE"
    report["revision"] = "R17_R13_TF_SPI_STAGING"
    report["state"] = "R17_R13_TF_SPI_ROUTED_CANDIDATE" if passed else "R17_R13_TF_SPI_HOLD"
    report["overall_status"] = "ROUTING_SCOPE_VERIFIED_WHOLE_BOARD_HOLD" if passed else "HOLD"
    report["locally_verified"] = False
    report["source"] = {
        "role": "sole_editable_PCB_geometry_source",
        "path": str(SOURCE_BOARD),
        "sha256": SOURCE_SHA256,
    }
    report["builder"] = {
        "path": str(Path(__file__).resolve()),
        "sha256": sha256_file(Path(__file__).resolve()),
        "routing_uuid_seed": ROUTING_UUID_SEED,
        "engine": {"path": str(ENGINE), "sha256": ENGINE_SHA256},
    }
    report["tf_spi_route_summary"] = LAST_ROUTE_SUMMARY
    report["completed_scope"] = sorted(ALLOWED_NETS) if passed else []
    report["inherited_completed_scope"] = (
        [
            "/DCDC_EN",
            "/BOOT_N",
            "/PS_HOLD",
            "/PWR_BUTTON_N",
            "/USER_KEY_1_N",
            "/USER_KEY_2_N",
        ]
        if passed
        else []
    )
    report["holds"] = [
        {
            "scope": "WHOLE_BOARD",
            "reason": "81 unrelated/held unconnected items remain; not manufacturing-ready",
        }
    ]
    if OUTPUT_BOARD.is_file():
        report["output"] = {
            "path": str(OUTPUT_BOARD),
            "bytes": OUTPUT_BOARD.stat().st_size,
            "sha256": sha256_file(OUTPUT_BOARD),
        }
    if passed:
        kicad_cli = base.find_kicad_cli()
        report.setdefault("artifacts", {})["isometric_preview"] = render_isometric(kicad_cli)
    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: Iterable[str] | None = None) -> int:
    if not SOURCE_BOARD.is_file() or sha256_file(SOURCE_BOARD) != SOURCE_SHA256:
        raise RouteError("sole source PCB missing or SHA-256 mismatched")
    configure_engine()
    exit_code = engine.main(argv)
    rewrite_report(exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
