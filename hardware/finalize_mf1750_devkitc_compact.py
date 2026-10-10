"""Finalize, reinforce, and verify the routed compact MF-1750 carrier."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
OUT = HARDWARE / "mf1750_devkitc_compact"
PROJECT = "mf1750_devkitc_compact"
INPUT = OUT / "freerouting_imported.kicad_pcb"
OUTPUT = OUT / f"{PROJECT}.kicad_pcb"

sys.path.insert(0, str(HARDWARE))
import prepare_mf1750_devkitc_compact_freerouting as prep  # noqa: E402


def configure_drc_severities() -> None:
    """Enable normally hidden geometry checks and isolate cosmetic deltas."""
    path = OUT / f"{PROJECT}.kicad_pro"
    data = json.loads(path.read_text(encoding="utf-8"))
    settings = data.setdefault("board", {}).setdefault("design_settings", {})
    severities = settings.setdefault("rule_severities", {})
    # The generated minimal project otherwise inherits several KiCad defaults
    # as "ignore".  Make those checks visible so DRC=0 is not achieved by an
    # accidental project-file omission.
    severities["missing_courtyard"] = "warning"
    severities["track_not_centered_on_via"] = "error"
    severities["footprint_filters_mismatch"] = "warning"
    severities["footprint_type_mismatch"] = "warning"
    severities["silk_edge_clearance"] = "warning"
    severities["lib_footprint_mismatch"] = "ignore"
    severities["silk_over_copper"] = "ignore"
    severities["silk_overlap"] = "ignore"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def mirror_bottom_testpoint_text(board) -> None:
    route = prep.route
    for index in range(1, 11):
        footprint = board.FindFootprintByReference(f"TP{index}")
        if footprint is None or footprint.GetLayer() != route.pcbnew.B_Cu:
            raise SystemExit(f"Bottom test-point identity mismatch: TP{index}")
        for field in footprint.GetFields():
            field.SetMirrored(True)
        for item in footprint.GraphicalItems():
            if isinstance(item, route.pcbnew.PCB_TEXT):
                item.SetMirrored(True)


def add_bottom_testpoint_labels(board) -> None:
    """Add unambiguous, short rail labels next to bottom-side probes."""
    route = prep.route
    labels = {
        "1:3V3": (4.0, 46.6),
        "2:GND": (8.0, 46.6),
        "3:VPH": (24.5, 23.6),
        "4:VGH": (28.5, 23.6),
        "5:VGL": (24.5, 39.6),
        "6:VPC": (59.5, 18.6),
        "7:VIO": (29.0, 39.6),
        "8:CS1": (36.0, 50.1),
        "9:CS2": (41.0, 50.1),
        "10:BUSY": (52.0, 50.1),
    }
    for footprint in board.GetFootprints():
        if not footprint.GetReference().startswith("TP"):
            continue
        for field in footprint.GetFields():
            field.SetVisible(False)
        for item in footprint.GraphicalItems():
            if isinstance(item, route.pcbnew.PCB_TEXT):
                item.SetVisible(False)
    for label, (x, y) in labels.items():
        item = route.pcbnew.PCB_TEXT(board)
        item.SetText(label)
        item.SetPosition(route.pcbnew.VECTOR2I_MM(x, y))
        item.SetLayer(route.pcbnew.B_SilkS)
        item.SetMirrored(True)
        item.SetTextSize(route.pcbnew.VECTOR2I_MM(0.80, 0.80))
        item.SetTextThickness(route.pcbnew.FromMM(0.12))
        board.Add(item)


def normalize_board_legends(board) -> None:
    """Place persistent top/bottom assembly and orientation legends."""
    route = prep.route
    for item in list(board.Drawings()):
        if not isinstance(item, route.pcbnew.PCB_TEXT):
            continue
        if item.GetText() == "MF1750 COMPACT B0":
            item.SetPosition(route.pcbnew.VECTOR2I_MM(30.0, 46.5))
        elif item.GetText() == "J3: 3V3 / GND":
            item.SetText("J3 P1=3V3 P2=GND")
            item.SetTextSize(route.pcbnew.VECTOR2I_MM(0.80, 0.80))
            item.SetTextThickness(route.pcbnew.FromMM(0.12))

    legends = (
        ("USB LEFT", 2.2, 45.0, 90.0),
        ("ANT RIGHT", 60.6, 44.5, 90.0),
        ("J2.1", 5.5, 54.0, 0.0),
        ("GND | +3V3", 10.5, 4.35, 0.0),
        ("R16 FIT / R15 DNP", 38.0, 35.6, 0.0),
    )
    for label, x, y, rotation in legends:
        item = route.pcbnew.PCB_TEXT(board)
        item.SetText(label)
        item.SetPosition(route.pcbnew.VECTOR2I_MM(x, y))
        item.SetLayer(route.pcbnew.F_SilkS)
        item.SetTextAngle(route.pcbnew.EDA_ANGLE(rotation, route.pcbnew.DEGREES_T))
        item.SetTextSize(route.pcbnew.VECTOR2I_MM(0.80, 0.80))
        item.SetTextThickness(route.pcbnew.FromMM(0.12))
        board.Add(item)


def normalize_connector_identity(board) -> None:
    """Match generated PCB connector values to the schematic identities."""
    values = {
        "J1": "MF-1750 50pin FPC",
        "J2": "ESP32-S3-DevKitC-1-N16R8 socket",
        "J3": "EPD 3V3 IN",
    }
    for ref, value in values.items():
        footprint = board.FindFootprintByReference(ref)
        if footprint is None:
            raise SystemExit(f"Missing connector footprint: {ref}")
        footprint.SetValue(value)


def configure_power_connector_zone_connections(board) -> None:
    """Give the load-bearing J3 ground pin a solid plane connection."""
    route = prep.route
    footprint = board.FindFootprintByReference("J3")
    pad = footprint.FindPadByNumber("2") if footprint is not None else None
    if pad is None or pad.GetNetname() != "/GND":
        raise SystemExit("J3 pin 2 is not the expected /GND power-entry pad")
    pad.SetLocalZoneConnection(route.pcbnew.ZONE_CONNECTION_FULL)


def configure_ground_zone_connections(board) -> None:
    """Solid-connect the antenna-edge socket ground where thermals starve."""
    route = prep.route
    footprint = board.FindFootprintByReference("J2")
    pad = footprint.FindPadByNumber("22") if footprint is not None else None
    if pad is None or pad.GetNetname() != "/GND":
        raise SystemExit("J2 pin 22 is not the expected /GND socket pad")
    pad.SetLocalZoneConnection(route.pcbnew.ZONE_CONNECTION_FULL)


def normalize_antenna_keepout(board) -> None:
    """Replace any routed-session antenna rule area with current geometry."""
    found = False
    for zone in list(board.Zones()):
        if zone.GetIsRuleArea() and zone.GetZoneName() == "DEVKITC_ANTENNA_KEEP_OUT":
            board.Remove(zone)
            found = True
    if not found:
        raise SystemExit("Routed board is missing DEVKITC_ANTENNA_KEEP_OUT")
    prep.add_antenna_keepout(board)


def _in_box(item, box: tuple[float, float, float, float], route) -> bool:
    x0, y0, x1, y1 = box
    points = (item.GetStart(), item.GetEnd())
    return all(
        x0 <= route.pcbnew.ToMM(point.x) <= x1
        and y0 <= route.pcbnew.ToMM(point.y) <= y1
        for point in points
    )


def reinforce_local_power_paths(board) -> dict[str, int]:
    """Widen supply segments only where the compact topology has clearance."""
    route = prep.route
    counts: dict[str, int] = {}
    # The dense routes cannot accept Rev A1's full-net widths without shorts.
    # These boxes select only the clear load-bearing input and converter paths;
    # Dense cross-board supply/bias segments remain at 0.20 mm and are a
    # documented B0 limit; these target nets do not terminate at J1/FPC pads.
    specs = {
        "/3V3_J3_UPPER": ("/3V3", (3.0, 0.5, 12.5, 19.0), 0.60),
        "/3V3_R4_R8": ("/3V3", (3.0, 43.5, 8.0, 45.5), 0.29),
        "/V_B_LOCAL": ("/V_B", (3.49, 26.5, 8.5, 29.0), 0.80),
        "/V_B_L1_FEED": ("/V_B", (7.5, 22.5, 13.0, 28.0), 0.80),
        "/V_B_R8_C23": ("/V_B", (8.5, 43.5, 12.0, 44.5), 0.80),
        "/EPD_3V3_R4": ("/EPD_3V3", (4.5, 42.0, 5.2, 44.5), 0.60),
        "/EPD_3V3_R6": ("/EPD_3V3", (17.3, 42.3, 18.0, 44.5), 0.60),
        "/SW_H": ("/SW_H", (12.0, 25.8, 15.5, 29.5), 0.45),
        "/SW_C": ("/SW_C", (39.5, 26.8, 46.0, 29.0), 0.40),
        "/VPH": ("/VPH", (18.0, 28.5, 22.0, 29.7), 0.45),
        "/VPC": ("/VPC", (54.7, 28.7, 60.0, 31.0), 0.45),
        "/NEG_PUMP_H": ("/NEG_PUMP_H", (6.0, 37.4, 10.0, 38.5), 0.40),
        "/RESEH": ("/RESEH", (16.8, 24.7, 19.3, 26.2), 0.40),
        "/RESEC": ("/RESEC", (48.7, 24.5, 56.0, 28.0), 0.40),
    }
    for label, (netname, box, width) in specs.items():
        count = 0
        for item in board.GetTracks():
            if (
                type(item) is route.pcbnew.PCB_TRACK
                and item.GetNetname() == netname
                and _in_box(item, box, route)
            ):
                item.SetWidth(route.pcbnew.FromMM(width))
                count += 1
        if not count:
            raise SystemExit(f"No local segments selected for reinforcement: {label}")
        counts[label] = count
    return counts


def add_ground_zones(board) -> None:
    route = prep.route
    gnd = board.GetNetcodeFromNetname("/GND")
    if not gnd:
        raise SystemExit("Missing /GND net")
    for zone in list(board.Zones()):
        if not zone.GetIsRuleArea():
            board.Remove(zone)
    for layer in (route.pcbnew.F_Cu, route.pcbnew.B_Cu):
        zone = route.pcbnew.ZONE(board)
        zone.SetLayer(layer)
        zone.SetNetCode(gnd)
        zone.SetZoneName("GND_PLANE")
        zone.SetLocalClearance(route.pcbnew.FromMM(0.20))
        zone.SetMinThickness(route.pcbnew.FromMM(0.20))
        zone.SetPadConnection(route.pcbnew.ZONE_CONNECTION_THERMAL)
        zone.SetThermalReliefGap(route.pcbnew.FromMM(0.25))
        zone.SetThermalReliefSpokeWidth(route.pcbnew.FromMM(0.30))
        outline = zone.Outline()
        polygon = outline.NewOutline()
        for x, y in ((0.65, 0.65), (61.35, 0.65), (61.35, 57.35), (0.65, 57.35)):
            outline.Append(route.pcbnew.VECTOR2I_MM(x, y), polygon)
        board.Add(zone)
    route.pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def add_supply_zones(board) -> None:
    """Reinforce the routed 3V3 input corridor and preserve most GND."""
    route = prep.route
    code = board.GetNetcodeFromNetname("/3V3")
    if not code:
        raise SystemExit("Missing /3V3 net")
    polygons = (
        # J3-to-R4/R8 input corridor beside the left edge, including TP1.
        (
            (10.95, 1.0),
            (11.95, 1.0),
            (11.95, 16.8),
            (2.0, 18.4),
            (1.45, 19.0),
            (1.45, 42.2),
            (4.35, 44.35),
            (7.4, 43.55),
            (7.9, 44.15),
            (4.0, 45.35),
            (3.3, 44.95),
            (3.55, 48.0),
            (4.45, 48.0),
            (4.45, 44.75),
            (3.0, 44.75),
            (0.65, 42.9),
            (0.65, 18.5),
            (1.6, 17.5),
            (10.95, 15.9),
        ),
    )
    for polygon_points in polygons:
        zone = route.pcbnew.ZONE(board)
        zone.SetLayer(route.pcbnew.B_Cu)
        zone.SetNetCode(code)
        zone.SetZoneName("J3_3V3_PARTIAL_RELIEF")
        zone.SetAssignedPriority(1)
        zone.SetLocalClearance(route.pcbnew.FromMM(0.20))
        zone.SetMinThickness(route.pcbnew.FromMM(0.20))
        zone.SetPadConnection(route.pcbnew.ZONE_CONNECTION_FULL)
        outline = zone.Outline()
        polygon = outline.NewOutline()
        for x, y in polygon_points:
            outline.Append(route.pcbnew.VECTOR2I_MM(x, y), polygon)
        board.Add(zone)
    route.pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def audit_supply_reinforcement(board) -> dict[str, object]:
    """Record actual filled-zone coverage without overstating continuity."""
    route = prep.route
    zones = [
        zone for zone in board.Zones() if zone.GetZoneName() == "J3_3V3_PARTIAL_RELIEF"
    ]
    if len(zones) != 1:
        raise SystemExit(f"Expected one 3V3 reinforcement zone, found {len(zones)}")
    filled = zones[0].GetFilledPolysList(route.pcbnew.B_Cu)
    checkpoints = {
        "j3_input": (11.5, 1.8),
        "upper_corridor": (3.3, 17.9),
        "left_mid_y30": (1.5, 30.0),
        "left_mid_y40": (1.5, 40.0),
        "r4_r8_via": (3.7, 45.0),
    }
    coverage = {
        label: filled.Contains(route.pcbnew.VECTOR2I_MM(*point))
        for label, point in checkpoints.items()
    }
    return {
        "filled_outline_count": filled.OutlineCount(),
        "checkpoint_coverage": coverage,
        "continuous_j3_to_r4_r8": False,
    }


def main() -> None:
    prep.configure_modules()
    route = prep.route
    board = route.pcbnew.LoadBoard(str(INPUT))
    if board is None:
        raise SystemExit(f"Cannot load {INPUT}")
    route.link_footprints_to_schematic(board)
    route.verify_board_pin_nets(board)
    mirror_bottom_testpoint_text(board)
    add_bottom_testpoint_labels(board)
    normalize_board_legends(board)
    normalize_connector_identity(board)
    configure_power_connector_zone_connections(board)
    configure_ground_zone_connections(board)
    normalize_antenna_keepout(board)
    widened = reinforce_local_power_paths(board)
    add_ground_zones(board)
    add_supply_zones(board)
    supply_zone_audit = audit_supply_reinforcement(board)
    route.pcbnew.SaveBoard(str(OUTPUT), board)
    configure_drc_severities()
    print(
        json.dumps(
            {
                "board": str(OUTPUT),
                "supply_zone_audit": supply_zone_audit,
                "widened_segments": widened,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
