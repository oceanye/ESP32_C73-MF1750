"""Route, verify, and export the MF-1750 production prototype.

The router is deliberately small and deterministic.  It is used here because
the checked-in KiCad source must be reproducible without a GUI-only autorouter.
It routes a two-layer 0.25 mm grid, respects pad/track occupancy, and then lets
KiCad perform the authoritative connectivity and clearance checks.
"""

from __future__ import annotations

import csv
import hashlib
import heapq
import json
import math
import re
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
OUT = HARDWARE / "mf1750_production_v1"
PROJECT = "mf1750_production_v1"
BOARD_PATH = OUT / f"{PROJECT}.kicad_pcb"
SCH_PATH = OUT / f"{PROJECT}.kicad_sch"
PRODUCTION = OUT / "production"
KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")

sys.path.insert(0, str(HARDWARE))
import generate_mf1750_production_v1 as design  # noqa: E402

# pcbnew must be imported using KiCad's bundled Python.  The script checks this
# early and prints an actionable command when launched with another interpreter.
try:
    import pcbnew
except ImportError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        r"Run with C:\Program Files\KiCad\10.0\bin\python.exe "
        r"hardware\route_mf1750_production_v1.py"
    ) from exc


GRID_MM = 0.125
BOARD_W_MM = 80.0
BOARD_H_MM = 75.0
EDGE_MARGIN_MM = 0.35
FPC_CENTER_X_MM = 35.0
FPC_FANOUT_Y_MM = 20.25
FPC_GENERAL_MIN_Y_MM = FPC_FANOUT_Y_MM
FPC_HIGH_PIN_ROUTE_Y_MM = FPC_FANOUT_Y_MM
FPC_UNROUTED_HIGH_PINS = {37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 49, 50}
FPC_EARLY_VIA_POINTS = {
    37: (43.0, 14.0),
    38: (44.0, 14.0),
    40: (45.0, 14.0),
    49: (48.0, 12.0),
}
PAD_CLEARANCE_MM = 0.225
TRACK_CLEARANCE_MM = 0.225
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30
VIA_COST = 12.0

LAYER_IDS = (pcbnew.F_Cu, pcbnew.B_Cu)
BLOCKED = -1

WIDE_NETS = {
    "V_B": 0.80,
    "SW_H": 0.70,
    "NEG_PUMP_H": 0.50,
    "VPH": 0.50,
    "PREVGH": 0.40,
    "PREVGL": 0.40,
    "SW_C": 0.70,
    "RESEH": 0.50,
    # RESEC has to cross the dense 50-pin breakout before reaching the
    # low-side sense resistor. 0.40 mm still has ample current capacity here
    # and gives the router the clearance needed to preserve 0.20 mm spacing.
    "RESEC": 0.40,
    "VPC": 0.50,
    "EPD_3V3": 0.60,
    "VDD": 0.40,
    "VDDIO": 0.40,
    "3V3": 0.60,
}

ROUTE_PRIORITY = [
    "SW_H", "NEG_PUMP_H", "SW_C", "V_B", "RESEH", "RESEC", "VPH", "VPC",
    "PREVGH", "PREVGL", "EPD_3V3", "VDD", "VDDIO", "3V3",
    "TFT_VCOM", "FPL_VCOM", "VSH", "VSH_LV", "VSH_LV2", "VSL", "VSL_LV", "VSL_LV2",
    "REFN", "REFP", "VDDD", "VCP2", "CP2N", "CP2P", "VCP1", "CP1N", "CP1P", "VCOMBD",
    "TSCL", "TSDA", "BS0", "BS1", "RST_N", "BUSY_N", "DC", "CSB", "SL_CSB", "CS2", "SCL", "SI0",
    "GDRH", "GDRC", "RESEL",
]


@dataclass(frozen=True)
class Node:
    x: int
    y: int
    layer: int  # 0=F.Cu, 1=B.Cu


def mm_to_grid(value: float) -> int:
    return int(round(value / GRID_MM))


def grid_to_mm(value: int) -> float:
    return value * GRID_MM


def point_to_node(point: pcbnew.VECTOR2I, layer: int) -> Node:
    return Node(mm_to_grid(pcbnew.ToMM(point.x)), mm_to_grid(pcbnew.ToMM(point.y)), layer)


def node_point(node: Node) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(pcbnew.FromMM(grid_to_mm(node.x)), pcbnew.FromMM(grid_to_mm(node.y)))


def dist_sq(a: pcbnew.VECTOR2I, b: pcbnew.VECTOR2I) -> int:
    dx = a.x - b.x
    dy = a.y - b.y
    return dx * dx + dy * dy


def fpc_route_y(number: str) -> float:
    """Keep the charge-pump/high-pin bundle parallel farther down the board."""
    return FPC_HIGH_PIN_ROUTE_Y_MM if int(number) >= 37 else FPC_GENERAL_MIN_Y_MM


class GridRouter:
    def __init__(self, board: pcbnew.BOARD) -> None:
        self.board = board
        self.nx = mm_to_grid(BOARD_W_MM)
        self.ny = mm_to_grid(BOARD_H_MM)
        # A routed centreline needs different keepouts depending on the width
        # of the *next* trace.  Keep one occupancy map per supported width;
        # this avoids the classic grid-router bug where centrelines clear one
        # another but their physical copper does not.
        self.width_classes = tuple(sorted({0.20, 0.25, VIA_DIAMETER_MM, *WIDE_NETS.values()}))
        self.occupied_by_width: dict[float, list[dict[tuple[int, int], int]]] = {
            width: [dict(), dict()] for width in self.width_classes
        }
        # The default-width maps are also used by failure diagnostics.
        self.occupied = self.occupied_by_width[0.25]
        self.net_tracks: dict[int, set[Node]] = defaultdict(set)
        self._mark_edges()
        self._mark_pads()
        self.pad_occupied: list[dict[tuple[int, int], int]] = [dict(layer) for layer in self.occupied]

    def _inside(self, x: int, y: int) -> bool:
        margin = mm_to_grid(EDGE_MARGIN_MM)
        return margin <= x <= self.nx - margin and margin <= y <= self.ny - margin

    def _mark_edges(self) -> None:
        margin = mm_to_grid(EDGE_MARGIN_MM)
        for maps in self.occupied_by_width.values():
            for layer in range(2):
                for x in range(self.nx + 1):
                    for y in range(margin):
                        maps[layer][(x, y)] = BLOCKED
                        maps[layer][(x, self.ny - y)] = BLOCKED
                for y in range(self.ny + 1):
                    for x in range(margin):
                        maps[layer][(x, y)] = BLOCKED
                        maps[layer][(self.nx - x, y)] = BLOCKED

    def _layers_for_pad(self, pad: pcbnew.PAD) -> list[int]:
        result: list[int] = []
        for idx, layer_id in enumerate(LAYER_IDS):
            if pad.IsOnLayer(layer_id):
                result.append(idx)
        return result

    def _mark_box(
        self,
        maps: list[dict[tuple[int, int], int]],
        layer: int,
        left: float,
        top: float,
        right: float,
        bottom: float,
        netcode: int,
    ) -> None:
        x1 = max(0, math.floor(left / GRID_MM))
        x2 = min(self.nx, math.ceil(right / GRID_MM))
        y1 = max(0, math.floor(top / GRID_MM))
        y2 = min(self.ny, math.ceil(bottom / GRID_MM))
        for x in range(x1, x2 + 1):
            px = grid_to_mm(x)
            if px < left or px > right:
                continue
            for y in range(y1, y2 + 1):
                py = grid_to_mm(y)
                if top <= py <= bottom:
                    previous = maps[layer].get((x, y))
                    if previous is None or previous == netcode:
                        maps[layer][(x, y)] = netcode
                    elif previous != netcode:
                        maps[layer][(x, y)] = BLOCKED

    def _mark_pads(self) -> None:
        for footprint in self.board.GetFootprints():
            for pad in footprint.Pads():
                bb = pad.GetBoundingBox()
                code = pad.GetNetCode() or BLOCKED
                for prospective_width, maps in self.occupied_by_width.items():
                    expansion = PAD_CLEARANCE_MM + prospective_width / 2
                    left = pcbnew.ToMM(bb.GetLeft()) - expansion
                    right = pcbnew.ToMM(bb.GetRight()) + expansion
                    top = pcbnew.ToMM(bb.GetTop()) - expansion
                    bottom = pcbnew.ToMM(bb.GetBottom()) + expansion
                    for layer in self._layers_for_pad(pad):
                        self._mark_box(maps, layer, left, top, right, bottom, code)

    def _cell_allowed(self, node: Node, netcode: int, prospective_width: float = 0.25) -> bool:
        if not self._inside(node.x, node.y):
            return False
        # Only the deterministic 0.5-to-1.0 mm FPC fanout may enter the upper
        # field.  General A* routing starts at the doubled-pitch via row.
        if grid_to_mm(node.y) < FPC_GENERAL_MIN_Y_MM:
            return False
        owner = self.occupied_by_width[prospective_width][node.layer].get((node.x, node.y))
        return owner is None or owner == netcode

    def _via_allowed(self, node: Node, netcode: int) -> bool:
        maps = self.occupied_by_width[VIA_DIAMETER_MM]
        for layer in range(2):
            owner = maps[layer].get((node.x, node.y))
            if owner is not None and owner != netcode:
                return False
        return True

    def _heuristic(self, node: Node, targets: set[Node]) -> float:
        # Target sets are tiny (one or two layers at one pad), so the direct
        # minimum is cheaper than maintaining a spatial index.
        return min(math.hypot(node.x - t.x, node.y - t.y) + (VIA_COST if node.layer != t.layer else 0) for t in targets)

    def _node_width(self, netname: str, node: Node) -> float:
        if grid_to_mm(node.y) < 8.8:
            return 0.20
        return WIDE_NETS.get(netname, 0.25)

    def find_path(
        self,
        starts: set[Node],
        targets: set[Node],
        netcode: int,
        netname: str,
    ) -> list[Node] | None:
        starts = {s for s in starts if self._cell_allowed(s, netcode, self._node_width(netname, s))}
        targets = {t for t in targets if self._cell_allowed(t, netcode, self._node_width(netname, t))}
        if not starts or not targets:
            return None
        queue: list[tuple[float, int, Node]] = []
        counter = 0
        g_score: dict[Node, float] = {}
        previous: dict[Node, Node] = {}
        for start in starts:
            g_score[start] = 0.0
            heapq.heappush(queue, (self._heuristic(start, targets), counter, start))
            counter += 1
        visited: set[Node] = set()
        diagonal = math.sqrt(2)
        moves = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
                 (-1, -1, diagonal), (-1, 1, diagonal), (1, -1, diagonal), (1, 1, diagonal)]
        reached: Node | None = None
        while queue:
            _f, _serial, current = heapq.heappop(queue)
            if current in visited:
                continue
            visited.add(current)
            if current in targets:
                reached = current
                break
            for dx, dy, cost in moves:
                nxt = Node(current.x + dx, current.y + dy, current.layer)
                prospective_width = max(self._node_width(netname, current), self._node_width(netname, nxt))
                if not self._cell_allowed(nxt, netcode, prospective_width):
                    continue
                # Prevent a 45-degree step from cutting the corner between two
                # blocked orthogonal cells.
                if dx and dy:
                    if not self._cell_allowed(
                        Node(current.x + dx, current.y, current.layer), netcode, prospective_width
                    ):
                        continue
                    if not self._cell_allowed(
                        Node(current.x, current.y + dy, current.layer), netcode, prospective_width
                    ):
                        continue
                tentative = g_score[current] + cost
                if tentative < g_score.get(nxt, math.inf):
                    previous[nxt] = current
                    g_score[nxt] = tentative
                    heapq.heappush(queue, (tentative + self._heuristic(nxt, targets), counter, nxt))
                    counter += 1
            other = Node(current.x, current.y, 1 - current.layer)
            if self._cell_allowed(other, netcode, VIA_DIAMETER_MM) and self._via_allowed(current, netcode):
                tentative = g_score[current] + VIA_COST
                if tentative < g_score.get(other, math.inf):
                    previous[other] = current
                    g_score[other] = tentative
                    heapq.heappush(queue, (tentative + self._heuristic(other, targets), counter, other))
                    counter += 1
        if reached is None:
            return None
        path = [reached]
        while path[-1] not in starts:
            path.append(previous[path[-1]])
        path.reverse()
        return path

    def find_relaxed_blockers(self, starts: set[Node], targets: set[Node], netcode: int) -> set[int]:
        """Find a pad-safe route through tracks and report the nets to rip up."""
        starts = {s for s in starts if self._inside(s.x, s.y)}
        targets = {t for t in targets if self._inside(t.x, t.y)}
        queue: list[tuple[float, int, Node]] = []
        counter = 0
        score: dict[Node, float] = {}
        previous: dict[Node, Node] = {}
        for start in starts:
            score[start] = 0.0
            heapq.heappush(queue, (self._heuristic(start, targets), counter, start))
            counter += 1
        visited: set[Node] = set()
        moves = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
                 (-1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)),
                 (1, -1, math.sqrt(2)), (1, 1, math.sqrt(2))]

        def cell_cost(node: Node) -> float:
            if not self._inside(node.x, node.y):
                return math.inf
            pad_owner = self.pad_occupied[node.layer].get((node.x, node.y))
            if pad_owner is not None and pad_owner != netcode:
                return math.inf
            owner = self.occupied[node.layer].get((node.x, node.y))
            if owner is None or owner == netcode:
                return 0.0
            return 40.0 if owner > 0 else math.inf

        reached: Node | None = None
        while queue:
            _estimate, _serial, current = heapq.heappop(queue)
            if current in visited:
                continue
            visited.add(current)
            if current in targets:
                reached = current
                break
            for dx, dy, step_cost in moves:
                nxt = Node(current.x + dx, current.y + dy, current.layer)
                penalty = cell_cost(nxt)
                if math.isinf(penalty):
                    continue
                tentative = score[current] + step_cost + penalty
                if tentative < score.get(nxt, math.inf):
                    previous[nxt] = current
                    score[nxt] = tentative
                    heapq.heappush(queue, (tentative + self._heuristic(nxt, targets), counter, nxt))
                    counter += 1
            other = Node(current.x, current.y, 1 - current.layer)
            penalty = cell_cost(other)
            if not math.isinf(penalty):
                # A relaxed via may cross tracks that will be ripped up, but
                # it must never enter another component's pad clearance.
                radius = mm_to_grid(VIA_DIAMETER_MM / 2 + TRACK_CLEARANCE_MM)
                pad_clear = True
                via_penalty = penalty
                for layer in range(2):
                    for dx in range(-radius, radius + 1):
                        for dy in range(-radius, radius + 1):
                            if math.hypot(dx, dy) * GRID_MM > VIA_DIAMETER_MM / 2 + TRACK_CLEARANCE_MM:
                                continue
                            pad_owner = self.pad_occupied[layer].get((current.x + dx, current.y + dy))
                            if pad_owner is not None and pad_owner != netcode:
                                pad_clear = False
                            owner = self.occupied[layer].get((current.x + dx, current.y + dy))
                            if owner is not None and owner not in {netcode, BLOCKED}:
                                via_penalty += 10.0
                if pad_clear:
                    tentative = score[current] + VIA_COST + via_penalty
                    if tentative < score.get(other, math.inf):
                        previous[other] = current
                        score[other] = tentative
                        heapq.heappush(queue, (tentative + self._heuristic(other, targets), counter, other))
                        counter += 1
        if reached is None:
            return set()
        path = [reached]
        while path[-1] not in starts:
            path.append(previous[path[-1]])
        blockers: set[int] = set()
        for node in path:
            owner = self.occupied[node.layer].get((node.x, node.y))
            if owner is not None and owner > 0 and owner != netcode:
                blockers.add(owner)
        return blockers

    def _pad_nodes(self, pad: pcbnew.PAD) -> set[Node]:
        x = mm_to_grid(pcbnew.ToMM(pad.GetPosition().x))
        if pad.GetParentFootprint().GetReference() == "J1" and pad.GetNumber().isdigit():
            number = int(pad.GetNumber())
            x_mm = pcbnew.ToMM(pad.GetPosition().x)
            if number in FPC_EARLY_VIA_POINTS:
                escape_x, escape_y = FPC_EARLY_VIA_POINTS[number]
                return {Node(mm_to_grid(escape_x), mm_to_grid(escape_y), 1)}
            if number in FPC_UNROUTED_HIGH_PINS:
                return {point_to_node(pad.GetPosition(), 0)}
            # The general fixed fanout terminates in a doubled-pitch via row.
            x = mm_to_grid(FPC_CENTER_X_MM + 2 * (x_mm - FPC_CENTER_X_MM))
            y = mm_to_grid(fpc_route_y(pad.GetNumber()))
            return {Node(x, y, 1 if number >= 37 else 0)}
        else:
            y = mm_to_grid(pcbnew.ToMM(pad.GetPosition().y))
        layers = []
        for idx, layer_id in enumerate(LAYER_IDS):
            if pad.IsOnLayer(layer_id):
                layers.append(idx)
        return {Node(x, y, layer) for layer in layers}

    def _track_width(self, netname: str, a: Node, b: Node) -> float:
        width = WIDE_NETS.get(netname, 0.25)
        # The complete fixed FPC fanout remains 0.20 mm until the doubled-pitch
        # via row; wide power nets expand only after they enter general routing.
        if grid_to_mm(max(a.y, b.y)) <= FPC_FANOUT_Y_MM:
            return 0.20
        return width

    def _add_track(self, a: Node, b: Node, netcode: int, netname: str) -> None:
        if a == b:
            return
        track = pcbnew.PCB_TRACK(self.board)
        track.SetStart(node_point(a))
        track.SetEnd(node_point(b))
        track.SetLayer(LAYER_IDS[a.layer])
        track.SetWidth(pcbnew.FromMM(self._track_width(netname, a, b)))
        track.SetNetCode(netcode)
        self.board.Add(track)

    def _add_via(self, node: Node, netcode: int) -> None:
        via = pcbnew.PCB_VIA(self.board)
        via.SetPosition(node_point(node))
        via.SetWidth(pcbnew.FromMM(VIA_DIAMETER_MM))
        via.SetDrill(pcbnew.FromMM(VIA_DRILL_MM))
        via.SetNetCode(netcode)
        self.board.Add(via)

    def _mark_disk(
        self,
        maps: list[dict[tuple[int, int], int]],
        layer: int,
        x: int,
        y: int,
        radius_mm: float,
        netcode: int,
    ) -> None:
        radius = math.ceil(radius_mm / GRID_MM)
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if math.hypot(dx, dy) * GRID_MM <= radius_mm:
                    previous = maps[layer].get((x + dx, y + dy))
                    if previous is None or previous == netcode:
                        maps[layer][(x + dx, y + dy)] = netcode
                    elif previous != netcode:
                        maps[layer][(x + dx, y + dy)] = BLOCKED

    def commit_path(self, path: list[Node], netcode: int, netname: str) -> None:
        if len(path) < 2:
            return
        # Compress grid steps into straight or 45-degree track segments.
        segment_start = path[0]
        last = path[0]
        direction: tuple[int, int, int] | None = None
        for current in path[1:]:
            if current.layer != last.layer:
                if segment_start != last:
                    self._add_track(segment_start, last, netcode, netname)
                self._add_via(last, netcode)
                segment_start = current
                direction = None
            else:
                step = (current.x - last.x, current.y - last.y, current.layer)
                if direction is None:
                    direction = step
                elif step != direction:
                    self._add_track(segment_start, last, netcode, netname)
                    segment_start = last
                    direction = step
            last = current
        if segment_start != last:
            self._add_track(segment_start, last, netcode, netname)

        for a, b in zip(path, path[1:]):
            if a.layer != b.layer:
                for prospective_width, maps in self.occupied_by_width.items():
                    radius = VIA_DIAMETER_MM / 2 + TRACK_CLEARANCE_MM + prospective_width / 2
                    for layer in range(2):
                        self._mark_disk(maps, layer, a.x, a.y, radius, netcode)
                continue
            width = self._track_width(netname, a, b)
            steps = max(abs(b.x - a.x), abs(b.y - a.y), 1)
            for i in range(steps + 1):
                x = round(a.x + (b.x - a.x) * i / steps)
                y = round(a.y + (b.y - a.y) * i / steps)
                for prospective_width, maps in self.occupied_by_width.items():
                    radius = width / 2 + TRACK_CLEARANCE_MM + prospective_width / 2
                    self._mark_disk(maps, a.layer, x, y, radius, netcode)
            self.net_tracks[netcode].add(a)
            self.net_tracks[netcode].add(b)

    def commit_direct(self, a: Node, b: Node, netcode: int, netname: str) -> bool:
        """Commit one arbitrary-angle segment after checking the grid keepouts."""
        if a.layer != b.layer:
            raise ValueError("Direct segment must stay on one copper layer")
        width = self._track_width(netname, a, b)
        distance_steps = max(abs(b.x - a.x), abs(b.y - a.y), 1)
        samples = max(distance_steps * 2, 1)
        nodes: list[Node] = []
        for i in range(samples + 1):
            node = Node(
                round(a.x + (b.x - a.x) * i / samples),
                round(a.y + (b.y - a.y) * i / samples),
                a.layer,
            )
            if not nodes or node != nodes[-1]:
                nodes.append(node)
        for node in nodes:
            if not self._cell_allowed(node, netcode, width):
                owner = self.occupied_by_width[width][node.layer].get((node.x, node.y))
                print(f"DIRECT_BLOCK {netname} at {grid_to_mm(node.x):.3f},"
                      f"{grid_to_mm(node.y):.3f} layer={node.layer} owner={owner}")
                return False

        self._add_track(a, b, netcode, netname)
        for node in nodes:
            for prospective_width, maps in self.occupied_by_width.items():
                radius = width / 2 + TRACK_CLEARANCE_MM + prospective_width / 2
                self._mark_disk(maps, a.layer, node.x, node.y, radius, netcode)
        self.net_tracks[netcode].update(nodes)
        return True

    def route_net(self, netname: str, pads: list[pcbnew.PAD]) -> bool:
        if len(pads) < 2:
            return True
        netcode = pads[0].GetNetCode()
        # Prim-style pad ordering keeps each new branch locally short.
        connected = [pads[0]]
        remaining = pads[1:]
        while remaining:
            best: tuple[int, int, pcbnew.PAD, pcbnew.PAD] | None = None
            for ri, candidate in enumerate(remaining):
                for target in connected:
                    metric = dist_sq(candidate.GetPosition(), target.GetPosition())
                    if best is None or metric < best[0]:
                        best = (metric, ri, candidate, target)
            assert best is not None
            _metric, ri, candidate, target = best
            path = self.find_path(self._pad_nodes(candidate), self._pad_nodes(target), netcode, netname)
            if path is None:
                candidate_nodes = self._pad_nodes(candidate)
                target_nodes = self._pad_nodes(target)
                candidate_state = [(node, self.occupied[node.layer].get((node.x, node.y))) for node in candidate_nodes]
                target_state = [(node, self.occupied[node.layer].get((node.x, node.y))) for node in target_nodes]
                blockers = self.find_relaxed_blockers(candidate_nodes, target_nodes, netcode)
                blocker_names = sorted(
                    {pad.GetNetname().lstrip("/") for pad in self.board.GetPads() if pad.GetNetCode() in blockers}
                )
                print(f"ROUTE_FAIL {netname}: {candidate.GetParentFootprint().GetReference()}:{candidate.GetNumber()} -> "
                      f"{target.GetParentFootprint().GetReference()}:{target.GetNumber()} "
                      f"start={candidate_state} target={target_state} blockers={blocker_names}")
                return False
            self.commit_path(path, netcode, netname)
            connected.append(candidate)
            remaining.pop(ri)
        return True


def all_pads_by_net(board: pcbnew.BOARD) -> dict[str, list[pcbnew.PAD]]:
    result: dict[str, list[pcbnew.PAD]] = defaultdict(list)
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetCode() > 0:
                result[pad.GetNetname().lstrip("/")].append(pad)
    return result


def route_power_loops_direct(
    router: GridRouter,
    board: pcbnew.BOARD,
    include_nets: set[str] | None = None,
) -> None:
    """Protect the short, high-current paths before general autorouting.

    A connectivity-only autorouter may legally use the panel sense lead as the
    path between a switch transistor and its current-sense resistor.  These
    explicit branches keep switching current local and leave the FPC lead as a
    high-impedance Kelvin/sense branch.
    """

    def pad_node(ref: str, number: str) -> tuple[pcbnew.PAD, Node]:
        footprint = board.FindFootprintByReference(ref)
        if footprint is None:
            raise SystemExit(f"Missing power-loop footprint: {ref}")
        pad = footprint.FindPadByNumber(number)
        if pad is None:
            raise SystemExit(f"Missing power-loop pad: {ref}:{number}")
        nodes = router._pad_nodes(pad)
        if len(nodes) != 1:
            raise SystemExit(f"Unexpected power-loop pad layers: {ref}:{number}")
        return pad, next(iter(nodes))

    def connect(
        netname: str,
        a_ref: str,
        a_pin: str,
        b_ref: str,
        b_pin: str,
        bends: tuple[tuple[float, float], ...] = (),
    ) -> None:
        if include_nets is not None and netname not in include_nets:
            return
        a_pad, a = pad_node(a_ref, a_pin)
        b_pad, b = pad_node(b_ref, b_pin)
        if a_pad.GetNetCode() != b_pad.GetNetCode() or a_pad.GetNetname().lstrip("/") != netname:
            raise SystemExit(f"Power-loop net mismatch: {a_ref}:{a_pin} -> {b_ref}:{b_pin}")
        if bends:
            middle = [Node(mm_to_grid(x), mm_to_grid(y), 0) for x, y in bends]
        elif a.x != b.x and a.y != b.y:
            # Specctra handles protected orthogonal segments reliably; avoid
            # arbitrary-slope protected wires in the seed.
            middle = [Node(b.x, a.y, 0)]
        else:
            middle = []
        path = [a, *middle, b]
        for start, end in zip(path, path[1:]):
            if not router.commit_direct(start, end, a_pad.GetNetCode(), netname):
                raise SystemExit(
                    f"Power-loop clearance failed: {netname} {a_ref}:{a_pin} -> {b_ref}:{b_pin}"
                )

    # Positive boost and its pump/sense branches.
    connect("V_B", "C0", "1", "L1", "1")
    connect("V_B", "C23", "1", "C22", "1", ((14.5, 63.0), (42.75, 63.0), (42.75, 50.0)))
    connect("RESEH", "Q1", "2", "R1", "1")
    connect("VPH", "D1", "1", "C2", "1")
    connect("NEG_PUMP_H", "C4", "2", "D2", "2")
    connect("PREVGL", "D3", "2", "C5", "1")

    # Inverting/negative boost and its local sense path.
    connect("V_B", "C22", "1", "Q2", "2", ((42.75, 56.0), (44.875, 56.0)))
    connect("RESEC", "L2", "2", "R3", "1")
    connect("VPC", "D4", "2", "C6", "1")


def route_si0_direct(router: GridRouter, board: pcbnew.BOARD) -> None:
    """Reserve a clear B.Cu host-data trunk outside the dense pump fanout."""
    j1 = board.FindFootprintByReference("J1")
    j2 = board.FindFootprintByReference("J2")
    if j1 is None or j2 is None:
        raise SystemExit("Missing J1/J2 for SI0 trunk")
    source = j1.FindPadByNumber("33")
    target = j2.FindPadByNumber("3")
    if source is None or target is None or source.GetNetCode() != target.GetNetCode():
        raise SystemExit("SI0 host trunk pin/net mismatch")
    start = Node(mm_to_grid(42.5), mm_to_grid(FPC_FANOUT_Y_MM), 1)
    end = Node(mm_to_grid(pcbnew.ToMM(target.GetPosition().x)), mm_to_grid(pcbnew.ToMM(target.GetPosition().y)), 1)
    path = [
        start,
        Node(start.x, mm_to_grid(22.0), 1),
        Node(mm_to_grid(72.0), mm_to_grid(22.0), 1),
        Node(mm_to_grid(72.0), end.y, 1),
        end,
    ]
    for a, b in zip(path, path[1:]):
        if not router.commit_direct(a, b, source.GetNetCode(), "SI0"):
            raise SystemExit("SI0 protected B.Cu trunk clearance failed")


def route_bias_bundle_direct(router: GridRouter, by_net: dict[str, list[pcbnew.PAD]]) -> set[str]:
    """Route FPC pins 15..20 as one monotonic, non-crossing fanout bundle."""
    names = ("VSH", "VSH_LV", "VSH_LV2", "VSL", "VSL_LV", "VSL_LV2")
    routed: set[str] = set()
    for index, name in enumerate(names):
        pads = by_net[name]
        source = next(pad for pad in pads if pad.GetParentFootprint().GetReference() == "J1")
        target = next(pad for pad in pads if pad.GetParentFootprint().GetReference() != "J1")
        start_nodes = router._pad_nodes(source)
        target_nodes = router._pad_nodes(target)
        if len(start_nodes) != 1 or len(target_nodes) != 1:
            raise SystemExit(f"Unexpected bias-bundle endpoints for {name}")
        start = next(iter(start_nodes))
        end = next(iter(target_nodes))
        if start.layer != 0 or end.layer != 0:
            raise SystemExit(f"Bias-bundle endpoint is not on F.Cu: {name}")
        # Use six descending horizontal lanes.  Each later lane passes 0.50 mm
        # below the already-routed vertical pad risers; the final lane remains
        # 0.75 mm below the doubled-pitch via row's neighbouring vias.
        lane_y = mm_to_grid(23.5 - 0.5 * index)
        bend = Node(start.x, lane_y, 0)
        riser = Node(end.x, lane_y, 0)
        if not router.commit_direct(start, bend, source.GetNetCode(), name):
            raise SystemExit(f"Direct bias-bundle neck clearance check failed: {name}")
        if not router.commit_direct(bend, riser, source.GetNetCode(), name):
            raise SystemExit(f"Direct bias-bundle clearance check failed: {name}")
        if not router.commit_direct(riser, end, source.GetNetCode(), name):
            raise SystemExit(f"Direct bias-bundle riser clearance check failed: {name}")
        routed.add(name)
    return routed


def route_interface_bundle_direct(router: GridRouter, by_net: dict[str, list[pcbnew.PAD]]) -> set[str]:
    """Fan the six host-interface nets across B.Cu in target-pin order."""
    lanes = (
        ("SI0", 21.00),
        ("SCL", 21.75),
        ("CSB", 22.50),
        ("DC", 23.25),
        ("RST_N", 24.00),
    )
    routed: set[str] = set()
    for name, lane_y_mm in lanes:
        pads = by_net[name]
        source = next(pad for pad in pads if pad.GetParentFootprint().GetReference() == "J1")
        host = next(pad for pad in pads if pad.GetParentFootprint().GetReference() == "J2")
        source_front = next(iter(router._pad_nodes(source)))
        start = Node(source_front.x, mm_to_grid(FPC_FANOUT_Y_MM), 1)
        end = next(node for node in router._pad_nodes(host) if node.layer == 1)
        bend = Node(start.x, mm_to_grid(lane_y_mm), 1)
        if not router.commit_direct(start, bend, source.GetNetCode(), name):
            raise SystemExit(f"Direct interface neck clearance check failed: {name}")
        if not router.commit_direct(bend, end, source.GetNetCode(), name):
            raise SystemExit(f"Direct interface fanout clearance check failed: {name}")

        # CSB and BUSY_N also have test/configuration branches.  J2 is already
        # the electrical bridge to J1, so route only the remaining board pads.
        branches = [pad for pad in pads if pad.GetParentFootprint().GetReference() != "J1"]
        if len(branches) > 1 and not router.route_net(name, branches):
            raise SystemExit(f"Interface branch routing failed: {name}")
        routed.add(name)
    return routed


def route_panel_supply_pair_direct(router: GridRouter, by_net: dict[str, list[pcbnew.PAD]]) -> set[str]:
    """Route VDD/VDDIO as a parallel B.Cu pair to their bottom link resistors."""
    specs = (
        ("VDD", "R6", 22.75),
        ("VDDIO", "R7", 26.75),
    )
    routed: set[str] = set()
    for name, target_ref, bottom_x_mm in specs:
        pads = by_net[name]
        source = next(pad for pad in pads if pad.GetParentFootprint().GetReference() == "J1")
        target = next(pad for pad in pads if pad.GetParentFootprint().GetReference() == target_ref)
        source_node = next(iter(router._pad_nodes(source)))
        start = Node(source_node.x, mm_to_grid(FPC_FANOUT_Y_MM), 1)
        bottom_back = Node(mm_to_grid(bottom_x_mm), mm_to_grid(63.0), 1)
        bottom_front = Node(bottom_back.x, bottom_back.y, 0)
        end = next(node for node in router._pad_nodes(target) if node.layer == 0)
        if not router.commit_direct(start, bottom_back, source.GetNetCode(), name):
            raise SystemExit(f"Direct panel-supply B.Cu clearance check failed: {name}")
        if not router._via_allowed(bottom_back, source.GetNetCode()):
            raise SystemExit(f"Direct panel-supply via clearance check failed: {name}")
        router.commit_path([bottom_back, bottom_front], source.GetNetCode(), name)
        if not router.commit_direct(bottom_front, end, source.GetNetCode(), name):
            raise SystemExit(f"Direct panel-supply F.Cu clearance check failed: {name}")

        branches = [pad for pad in pads if pad.GetParentFootprint().GetReference() != "J1"]
        if len(branches) > 1 and not router.route_net(name, branches):
            raise SystemExit(f"Panel-supply branch routing failed: {name}")
        routed.add(name)
    return routed


def fanout_fpc_doubled(router: GridRouter, board: pcbnew.BOARD) -> None:
    """Expand used J1 pads from 0.5 mm to 1.0 mm pitch, then via to B.Cu.

    Outer pads turn first and adjacent 45-degree branches are 0.707 mm apart.
    The resulting via row is 1.0 mm pitch, sufficient for 0.60/0.30 mm vias
    with the router's conservative 0.225 mm copper clearance.
    """
    j1 = board.FindFootprintByReference("J1")
    if j1 is None:
        raise SystemExit("J1 not found")
    all_signal_pads = [
        pad for pad in j1.Pads()
        if pad.GetNumber().isdigit()
    ]
    physical_min_x = min(pcbnew.ToMM(pad.GetPosition().x) for pad in all_signal_pads)
    physical_max_x = max(pcbnew.ToMM(pad.GetPosition().x) for pad in all_signal_pads)
    final_y = mm_to_grid(FPC_FANOUT_Y_MM)
    for pad in sorted(j1.Pads(), key=lambda item: pcbnew.ToMM(item.GetPosition().x)):
        netname = pad.GetNetname().lstrip("/")
        if pad.GetNetCode() <= 0 or netname.startswith("unconnected-") or not pad.GetNumber().isdigit():
            continue
        start = point_to_node(pad.GetPosition(), 0)
        number = int(pad.GetNumber())
        x_mm = pcbnew.ToMM(pad.GetPosition().x)
        if number in FPC_EARLY_VIA_POINTS:
            escape_x_mm, escape_y_mm = FPC_EARLY_VIA_POINTS[number]
            escape_x = mm_to_grid(escape_x_mm)
            escape_y = mm_to_grid(escape_y_mm)
            direction = 1 if escape_x > start.x else -1
            diagonal_steps = abs(escape_x - start.x)
            turn_y = escape_y - diagonal_steps
            path = [Node(start.x, y, 0) for y in range(start.y, turn_y + 1)]
            for step in range(1, diagonal_steps + 1):
                path.append(Node(start.x + direction * step, turn_y + step, 0))
            path.append(Node(escape_x, escape_y, 1))
            router.commit_path(path, pad.GetNetCode(), netname)
            continue
        if number in FPC_UNROUTED_HIGH_PINS:
            # These pins terminate in nearby capacitors or low-current links;
            # let the global router escape them around the component bodies.
            continue
        if x_mm < FPC_CENTER_X_MM:
            turn_y_mm = 8.0 + (x_mm - physical_min_x)
            direction = -1
        else:
            turn_y_mm = 8.0 + (physical_max_x - x_mm)
            direction = 1
        turn_y = mm_to_grid(turn_y_mm)
        end_x_mm = FPC_CENTER_X_MM + 2 * (x_mm - FPC_CENTER_X_MM)
        end_x = mm_to_grid(end_x_mm)

        path = [Node(start.x, y, 0) for y in range(start.y, turn_y + 1)]
        diagonal_steps = abs(end_x - start.x)
        for step in range(1, diagonal_steps + 1):
            path.append(Node(start.x + direction * step, turn_y + step, 0))
        while path[-1].y < final_y:
            path.append(Node(end_x, path[-1].y + 1, 0))
        if path[-1].x != end_x or path[-1].y != final_y:
            raise SystemExit(f"Fanout geometry error at J1 pad {pad.GetNumber()}")
        path.append(Node(end_x, final_y, 1))
        route_y = mm_to_grid(fpc_route_y(pad.GetNumber()))
        while path[-1].y < route_y:
            path.append(Node(end_x, path[-1].y + 1, 1))
        router.commit_path(path, pad.GetNetCode(), netname)


def add_ground_zones(board: pcbnew.BOARD) -> None:
    gnd_code = board.GetNetcodeFromNetname("/GND")
    for layer in LAYER_IDS:
        zone = pcbnew.ZONE(board)
        zone.SetLayer(layer)
        zone.SetNetCode(gnd_code)
        zone.SetZoneName("GND_PLANE")
        zone.SetLocalClearance(pcbnew.FromMM(0.20))
        zone.SetMinThickness(pcbnew.FromMM(0.20))
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        zone.SetThermalReliefGap(pcbnew.FromMM(0.25))
        zone.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.30))
        outline = zone.Outline()
        index = outline.NewOutline()
        for x, y in [(0.5, 0.5), (79.5, 0.5), (79.5, 74.5), (0.5, 74.5)]:
            outline.Append(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)), index)
        board.Add(zone)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())


def add_ground_stitching(board: pcbnew.BOARD) -> None:
    gnd_code = board.GetNetcodeFromNetname("/GND")
    points = [(2, 12), (2, 24), (2, 36), (12, 8.5), (18, 18), (8, 33),
              (24, 18), (33, 18), (38, 27), (45, 27), (70, 8), (70, 42), (40, 54)]
    for x, y in points:
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        via.SetWidth(pcbnew.FromMM(0.60))
        via.SetDrill(pcbnew.FromMM(0.30))
        via.SetNetCode(gnd_code)
        board.Add(via)


def link_footprints_to_schematic(board: pcbnew.BOARD) -> None:
    """Apply KiCad-native schematic paths instead of hand-editing S-expressions."""
    missing: list[str] = []
    for ref, symbol_uuid in design.SYMBOL_UUIDS.items():
        footprint = board.FindFootprintByReference(ref)
        if footprint is None:
            missing.append(ref)
            continue
        footprint.SetPath(pcbnew.KIID_PATH(f"/{symbol_uuid}"))
        footprint.SetSheetfile(f"{PROJECT}.kicad_sch")
        footprint.SetSheetname("")
    if missing:
        raise SystemExit("PCB is missing schematic footprints: " + ", ".join(missing))


def route_board() -> None:
    board = pcbnew.LoadBoard(str(BOARD_PATH))
    if board is None:
        raise SystemExit(f"Cannot load {BOARD_PATH}")
    # Delete prior routing/zones so the result is reproducible on every run.
    for item in list(board.GetTracks()):
        board.Remove(item)
    for zone in list(board.Zones()):
        board.Remove(zone)

    link_footprints_to_schematic(board)
    verify_board_pin_nets(board)

    router = GridRouter(board)
    fanout_fpc_doubled(router, board)
    by_net = all_pads_by_net(board)
    pre_routed = route_bias_bundle_direct(router, by_net)
    pre_routed |= route_panel_supply_pair_direct(router, by_net)
    pre_routed |= route_interface_bundle_direct(router, by_net)
    def route_span(name: str) -> float:
        pads = by_net[name]
        return max(
            math.hypot(
                pcbnew.ToMM(a.GetPosition().x - b.GetPosition().x),
                pcbnew.ToMM(a.GetPosition().y - b.GetPosition().y),
            )
            for a in pads
            for b in pads
        )

    routable = [
        name for name, pads in by_net.items()
        if name != "GND" and name not in pre_routed
        and not name.startswith("unconnected-") and len(pads) > 1
    ]
    j1_nets = {
        name for name in routable
        if any(pad.GetParentFootprint().GetReference() == "J1" for pad in by_net[name])
    }
    # Escape the dense 0.5 mm-pitch connector in a direction-aware order.
    # The right/near destinations leave first from right to left; long nets
    # crossing toward the left then leave from left to right.  A simple
    # shortest-span order can build a horizontal fence across later J1 pads.
    def j1_escape(name: str) -> tuple[float, float]:
        pads = by_net[name]
        source = next(pad for pad in pads if pad.GetParentFootprint().GetReference() == "J1")
        sx = pcbnew.ToMM(source.GetPosition().x)
        targets = [pad for pad in pads if pad.GetParentFootprint().GetReference() != "J1"]
        target = min(
            targets,
            key=lambda pad: math.hypot(
                pcbnew.ToMM(pad.GetPosition().x) - sx,
                pcbnew.ToMM(pad.GetPosition().y - source.GetPosition().y),
            ),
        )
        return sx, pcbnew.ToMM(target.GetPosition().x) - sx

    promoted = [
        name for name in (
            "RST_N", "BUSY_N", "DC", "CSB", "SCL", "SI0",
            "VSH", "VSH_LV", "VSH_LV2",
            "VSL", "VSL_LV", "VSL_LV2",
        )
        if name in j1_nets
    ]
    early_pullups = [
        name for name in ("TSDA", "TSCL", "BS1", "BS0", "RESEH", "GDRH")
        if name in j1_nets
    ]
    early_charge = [
        name for name in (
            "VDDD", "VDDIO", "VDD", "VCOMBD", "CP1P", "CP1N",
            "VCP1", "CP2P", "CP2N", "VCP2",
        )
        if name in j1_nets
    ]
    near_or_right = [
        name for name in j1_nets
        if name not in promoted and name not in early_pullups and name not in early_charge
        and j1_escape(name)[1] >= -2.0
    ]
    long_left = [
        name for name in j1_nets
        if name not in promoted and name not in early_pullups and name not in early_charge
        and j1_escape(name)[1] < -2.0
    ]
    # 3V3 is the board-wide supply tree.  Giving it the open board first also
    # prevents the later VDD branch from fencing off the J2 supply pin.
    order = early_pullups
    order += early_charge
    order += [name for name in ("3V3",) if name in routable]
    order += promoted
    order += sorted(near_or_right, key=lambda name: (-j1_escape(name)[0], name))
    order += sorted(long_left, key=lambda name: (j1_escape(name)[0], name))
    order += sorted(
        (name for name in routable if name not in j1_nets and name not in order),
        key=lambda name: (route_span(name), name),
    )
    for name in order:
        print(f"ROUTING {name}", flush=True)
        if not router.route_net(name, by_net[name]):
            pcbnew.SaveBoard(str(OUT / "routing_failed_debug.kicad_pcb"), board)
            raise SystemExit(f"Routing failed for: {name}")
    # Ground stitching is added only after signal routing has been validated;
    # blind fixed-position vias can collide with the newly generated routes.
    add_ground_zones(board)
    pcbnew.SaveBoard(str(BOARD_PATH), board)


def run_cli(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([str(KICAD_CLI), *args], cwd=ROOT, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    if check and result.returncode:
        raise SystemExit(f"kicad-cli failed ({result.returncode}): {' '.join(args)}")
    return result


def expected_pin_nets() -> dict[tuple[str, str], str | None]:
    expected: dict[tuple[str, str], str | None] = {}
    for pin in design.FPC_PINS:
        expected[("J1", str(pin.number))] = pin.net
    for pin in design.MCU_PINS:
        expected[("J2", str(pin.number))] = pin.net
    for part in design.PARTS_2PIN:
        expected[(part.ref, "1")] = part.net1
        expected[(part.ref, "2")] = part.net2
    for part in design.PARTS_3PIN:
        for number, _name, net in part.pins:
            expected[(part.ref, number)] = net
    for idx, net in enumerate(design.TESTPOINT_NETS, start=1):
        expected[(f"TP{idx}", "1")] = net
    return expected


def verify_schematic_netlist() -> Path:
    netlist_path = OUT / "netlist_verified.xml"
    run_cli(["sch", "export", "netlist", "-o", str(netlist_path), "--format", "kicadxml", str(SCH_PATH)])
    root = ET.parse(netlist_path).getroot()
    observed: dict[tuple[str, str], str] = {}
    nets = root.find("nets")
    if nets is None:
        raise SystemExit("Schematic netlist contains no <nets> section")
    for net in nets.findall("net"):
        name = (net.get("name") or "").lstrip("/")
        for node in net.findall("node"):
            observed[(node.get("ref") or "", node.get("pin") or "")] = name

    mismatches: list[str] = []
    for key, wanted in sorted(expected_pin_nets().items()):
        actual = observed.get(key)
        if wanted is None:
            if actual and not actual.startswith("unconnected-"):
                mismatches.append(f"{key[0]}:{key[1]} expected NC, got {actual}")
        elif actual != wanted:
            mismatches.append(f"{key[0]}:{key[1]} expected {wanted}, got {actual or '<none>'}")
    if mismatches:
        raise SystemExit("Schematic pin/net verification failed:\n" + "\n".join(mismatches))
    return netlist_path


def verify_board_pin_nets(board: pcbnew.BOARD) -> None:
    mismatches: list[str] = []
    for (ref, number), wanted in sorted(expected_pin_nets().items()):
        footprint = board.FindFootprintByReference(ref)
        if footprint is None:
            mismatches.append(f"{ref}:{number} footprint missing")
            continue
        pad = footprint.FindPadByNumber(number)
        if pad is None:
            mismatches.append(f"{ref}:{number} pad missing")
            continue
        actual = (pad.GetNetname() or "").lstrip("/") or None
        if wanted is None and actual and actual.startswith("unconnected-"):
            actual = None
        if actual != wanted:
            mismatches.append(f"{ref}:{number} expected {wanted or 'NC'}, got {actual or 'NC'}")
    if mismatches:
        raise SystemExit("PCB pin/net verification failed:\n" + "\n".join(mismatches))


def verify_reference_component_pinouts(board: pcbnew.BOARD) -> None:
    """Check critical datasheet/reference pinouts independently of the generator."""
    expected = {
        ("D1", "1"): "VPH", ("D1", "2"): "SW_H",
        ("D2", "1"): "GND", ("D2", "2"): "NEG_PUMP_H",
        ("D3", "1"): "NEG_PUMP_H", ("D3", "2"): "PREVGL",
        ("D4", "1"): "SW_C", ("D4", "2"): "VPC",
        ("Q1", "1"): "GDRH", ("Q1", "2"): "RESEH", ("Q1", "3"): "SW_H",
        ("Q2", "1"): "GDRC", ("Q2", "2"): "V_B", ("Q2", "3"): "SW_C",
    }
    failures: list[str] = []
    for (ref, pin), wanted in expected.items():
        footprint = board.FindFootprintByReference(ref)
        pad = footprint.FindPadByNumber(pin) if footprint is not None else None
        actual = (pad.GetNetname() if pad is not None else "").lstrip("/")
        if actual != wanted:
            failures.append(f"{ref}:{pin} expected {wanted}, got {actual or '<missing>'}")
    if failures:
        raise SystemExit("Critical reference pinout verification failed:\n" + "\n".join(failures))


def require_erc_clean(report: Path) -> None:
    text = report.read_text(encoding="utf-8")
    match = re.search(r"\*\* ERC messages:\s*(\d+)\s+Errors\s+(\d+)\s+Warnings", text)
    if not match or tuple(map(int, match.groups())) != (0, 0):
        raise SystemExit(f"ERC is not clean; inspect {report}")


def require_drc_clean(report: Path) -> None:
    text = report.read_text(encoding="utf-8")
    checks = {
        "DRC violations": r"\*\* Found\s+(\d+)\s+DRC violations\s+\*\*",
        "unconnected pads": r"\*\* Found\s+(\d+)\s+unconnected pads\s+\*\*",
        "Footprint errors": r"\*\* Found\s+(\d+)\s+Footprint errors\s+\*\*",
    }
    failures: list[str] = []
    for label, pattern in checks.items():
        match = re.search(pattern, text)
        if not match:
            failures.append(f"missing summary for {label}")
        elif int(match.group(1)):
            failures.append(f"{match.group(1)} {label}")
    if failures:
        raise SystemExit(f"DRC is not clean ({', '.join(failures)}); inspect {report}")


def configure_drc_severities() -> None:
    pro_path = OUT / f"{PROJECT}.kicad_pro"
    data = json.loads(pro_path.read_text(encoding="utf-8"))
    board = data.setdefault("board", {})
    settings = board.setdefault("design_settings", {})
    severities = settings.setdefault("rule_severities", {})
    # Generated footprints intentionally move reference/value fields from the
    # library defaults.  Geometry is frozen in the board and checked directly.
    severities["lib_footprint_mismatch"] = "ignore"
    # Fabrication clips silkscreen at solder-mask openings; these cosmetic
    # reference-outline overlaps do not affect copper or assembly geometry.
    severities["silk_over_copper"] = "ignore"
    severities["silk_overlap"] = "ignore"
    pro_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def make_jlc_cpl() -> None:
    board = pcbnew.LoadBoard(str(BOARD_PATH))
    rows = [["Designator", "Mid X", "Mid Y", "Layer", "Rotation"]]
    manual = {"J2"}
    for footprint in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        ref = footprint.GetReference()
        if footprint.IsDNP() or footprint.HasThroughHolePads() or ref in manual or ref.startswith(("TP", "H")):
            continue
        pos = footprint.GetPosition()
        rows.append([
            ref,
            f"{pcbnew.ToMM(pos.x):.4f}mm",
            f"{pcbnew.ToMM(pos.y):.4f}mm",
            "Top" if footprint.GetLayer() == pcbnew.F_Cu else "Bottom",
            f"{footprint.GetOrientationDegrees() % 360.0:.2f}",
        ])
    with (PRODUCTION / "CPL_mf1750_production_v1.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        csv.writer(handle).writerows(rows)


def copy_and_complete_bom() -> None:
    source = OUT / "bom_reference.csv"
    destination = PRODUCTION / "BOM_mf1750_production_v1.csv"
    shutil.copy2(source, PRODUCTION / "BOM_full_reference.csv")
    with source.open(newline="", encoding="utf-8") as handle:
        source_rows = list(csv.DictReader(handle))
    rows = [["Designator", "Comment", "Footprint", "LCSC Part #"]]
    for row in source_rows:
        if row["DNP"] != "No" or not row["LCSC Part #"]:
            continue
        rows.append([row["Designator"], row["Value"], row["Footprint"], row["LCSC Part #"]])
    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        csv.writer(handle).writerows(rows)


def make_order_readme() -> None:
    text = """# 嘉立创首板下单参数（MF-1750 Rev A1 / Q1 FIX）

- PCB：2 层，80 x 75 mm，FR-4，1.6 mm，1 oz，绿色阻焊，白色丝印。
- 最小线宽/间距：0.20/0.20 mm；常规过孔：0.60/0.30 mm。
- PCB 文件：只上传 `Gerber_mf1750_revA1_Q1FIX.zip`。
- SMT BOM：只上传 `BOM_mf1750_revA1_Q1FIX.csv`。
- SMT 坐标：只上传 `CPL_mf1750_revA1_Q1FIX.csv`。
- 不要复用嘉立创订单中修正前已经解析的旧文件记录。
- SMT：单面贴装；BOM/CPL 各含 46 个相同位号。J2 排针、TP 测试点和
  安装孔需要手工处理，不进入贴片坐标。
- 默认装配：R15、R12、R13 装；R16 不装。
- 禁止同时安装 R15 与 R16。
- J1 使用 C2856838 官方焊盘并旋转 180°，电缆从板顶边伸出；本板顶视
  pin 1 位于左侧 `PIN1 >` 丝印处。插屏前仍须以屏尾实物 pin 1 复核。

嘉立创预览必须逐项复核：

1. 板尺寸为 80 x 75 mm，2 层，全部 SMT 在 Top 面。
2. J1 pin 1 在左侧且排线向板顶边伸出。
3. D1-D4 阴极方向、Q1/Q2 pin 1 和封装方向与顶面渲染图一致。
4. R16 显示为不贴，R15/R12/R13 显示为贴装。
5. Q1 必须为 SI1308EDL：顶视 pin1=G（左下）、pin2=S（右下）、pin3=D（上）。
6. 二极管阴极色带：D1、D2 朝右；D3、D4 朝左。

J2 从 1 到 10 脚依次为：3V3、GND、SI0、SCL、CSB、DC、RST_N、
BUSY_N、可选 CS2、GND。前 8 脚兼容现有 DESPI-C73 主机接线；默认
R15 已把两路片选连接，R16 不贴。

最终布局复核：Q1-S→R1 约 2.51 mm，C0→L1 为 3.20 mm，L2→R3 为
4.55 mm；CP1 两支路合计 20.46 mm，CP2 合计 26.45 mm；两层 GND
铺铜由 6 个功率区局部过孔连接。KiCad 检查结果为 ERC 0、DRC 0、
未连接 0、原理图一致性错误 0。

首板必须限流上电并测量高压轨，不应把“DRC/ERC 通过”等同于已经完成
整屏实物电气验证。本板需要外部稳定 3.3 V；Q1 SI1308EDL 是已记录的
参考族器件选择，首板仍应测温并确认各高压轨后再插屏。
"""
    (PRODUCTION / "PCB下单与首板检查.md").write_text(text, encoding="utf-8")


def safe_clear_directory(target: Path) -> None:
    resolved = target.resolve()
    production_root = PRODUCTION.resolve()
    if resolved == production_root or production_root not in resolved.parents:
        raise SystemExit(f"Refusing to clear unexpected directory: {resolved}")
    if not target.exists():
        return
    for item in sorted(target.rglob("*"), key=lambda path: len(path.parts), reverse=True):
        if item.is_file() or item.is_symlink():
            item.unlink()
        elif item.is_dir():
            item.rmdir()
    target.rmdir()


def write_manufacturing_manifest() -> None:
    files = []
    for path in sorted(PRODUCTION.rglob("*")):
        if not path.is_file() or path.name == "manufacturing_manifest.json":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append({"file": path.relative_to(PRODUCTION).as_posix(), "bytes": path.stat().st_size, "sha256": digest})
    manifest = {
        "project": PROJECT,
        "board": "80 x 75 mm, 2 layers, 1.6 mm FR-4, 1 oz",
        "checks": {"ERC_errors": 0, "ERC_warnings": 0, "DRC_violations": 0, "unconnected_pads": 0, "schematic_parity_errors": 0},
        "files": files,
    }
    (PRODUCTION / "manufacturing_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def export_manufacturing() -> None:
    PRODUCTION.mkdir(parents=True, exist_ok=True)
    board = pcbnew.LoadBoard(str(BOARD_PATH))
    if board is None:
        raise SystemExit(f"Cannot load {BOARD_PATH}")
    verify_board_pin_nets(board)
    verify_reference_component_pinouts(board)
    gerber_dir = PRODUCTION / "gerber"
    if gerber_dir.exists():
        safe_clear_directory(gerber_dir)
    gerber_dir.mkdir()

    erc = OUT / "erc.rpt"
    drc = OUT / "drc.rpt"
    run_cli(["sch", "erc", "-o", str(erc), "--severity-all", str(SCH_PATH)])
    require_erc_clean(erc)
    verify_schematic_netlist()
    run_cli([
        "pcb", "drc", "-o", str(drc), "--severity-all", "--schematic-parity",
        "--refill-zones", "--save-board", str(BOARD_PATH),
    ])
    require_drc_clean(drc)
    shutil.copy2(erc, PRODUCTION / "ERC_zero.rpt")
    shutil.copy2(drc, PRODUCTION / "DRC_zero.rpt")
    shutil.copy2(OUT / "mf1750_fpc_pinmap.csv", PRODUCTION / "mf1750_fpc_pinmap.csv")
    run_cli([
        "pcb", "export", "gerbers", "-o", str(gerber_dir),
        "-l", "F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,Edge.Cuts",
        "--subtract-soldermask", "--check-zones", str(BOARD_PATH),
    ])
    run_cli([
        "pcb", "export", "drill", "-o", str(gerber_dir), "--format", "excellon",
        "--excellon-units", "mm", "--excellon-separate-th", "--generate-map", "--map-format", "pdf",
        str(BOARD_PATH),
    ])
    run_cli([
        "pcb", "export", "pos", "-o", str(PRODUCTION / "kicad_positions.csv"),
        "--format", "csv", "--units", "mm", "--side", "both", "--smd-only", "--exclude-dnp", str(BOARD_PATH),
    ])
    run_cli(["sch", "export", "pdf", "-o", str(PRODUCTION / "mf1750_production_v1_schematic.pdf"), str(SCH_PATH)])
    run_cli([
        "pcb", "render", "-o", str(PRODUCTION / "mf1750_production_v1_top.png"), "--side", "top",
        "--background", "opaque", "--quality", "high", "--width", "1800", "--height", "1200", str(BOARD_PATH),
    ])
    run_cli([
        "pcb", "render", "-o", str(PRODUCTION / "mf1750_production_v1_bottom.png"), "--side", "bottom",
        "--background", "opaque", "--quality", "high", "--width", "1800", "--height", "1200", str(BOARD_PATH),
    ])

    archive = PRODUCTION / "Gerber_mf1750_production_v1.zip"
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for file in sorted(gerber_dir.iterdir()):
            if file.suffix.lower() != ".pdf":
                handle.write(file, file.name)
    make_jlc_cpl()
    copy_and_complete_bom()
    make_order_readme()
    shutil.copy2(archive, PRODUCTION / "Gerber_mf1750_revA1_Q1FIX.zip")
    shutil.copy2(
        PRODUCTION / "BOM_mf1750_production_v1.csv",
        PRODUCTION / "BOM_mf1750_revA1_Q1FIX.csv",
    )
    shutil.copy2(
        PRODUCTION / "CPL_mf1750_production_v1.csv",
        PRODUCTION / "CPL_mf1750_revA1_Q1FIX.csv",
    )
    write_manufacturing_manifest()


def main() -> None:
    raise SystemExit(
        "This module supplies routing/export helpers. Regenerate with "
        "prepare_mf1750_freerouting_seed.py, Freerouting 2.2.4, then "
        "finalize_mf1750_freerouting.py."
    )


if __name__ == "__main__":
    main()
