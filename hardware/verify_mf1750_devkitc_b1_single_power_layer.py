"""Fail-closed verifier for the preferred single-power-layer Rev B1 candidate."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
OUT = HARDWARE / "mf1750_devkitc_b1_single_power_layer"
PROJECT = "mf1750_devkitc_b1_single_power_layer"
BOARD = OUT / f"{PROJECT}.kicad_pcb"
SCHEMATIC = OUT / f"{PROJECT}.kicad_sch"
KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")

sys.path.insert(0, str(HARDWARE))
import prepare_mf1750_devkitc_compact_freerouting as prep  # noqa: E402


WIDTHS = {"/3V3": 0.50, "/EPD_3V3": 0.60, "/V_B": 0.80}
VIA_COUNTS = {"/3V3": 5, "/EPD_3V3": 4, "/V_B": 6}
GND_STITCHING_VIAS_MM = (
    (8.20, 1.80),
    (26.00, 10.00),
    (30.00, 11.00),
    (39.00, 11.00),
    (23.20, 29.00),
    (58.20, 27.525),
    (33.225, 30.40),
    (15.40, 44.00),
)


def run(*args: str) -> None:
    subprocess.run([str(KICAD_CLI), *args], cwd=ROOT, check=True)


def require(pattern: str, text: str, label: str) -> None:
    if not re.search(pattern, text):
        raise SystemExit(f"Missing clean {label} summary")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_board(board: pcbnew.BOARD) -> dict[str, object]:
    if board.GetCopperLayerCount() != 4:
        raise SystemExit("B1 must have exactly four copper layers")
    if not board.IsLayerEnabled(pcbnew.F_Paste) or not board.IsLayerEnabled(
        pcbnew.B_Paste
    ):
        raise SystemExit("F.Paste/B.Paste must be enabled for fabrication export")
    in1_tracks = [
        item
        for item in board.GetTracks()
        if type(item) is pcbnew.PCB_TRACK and item.GetLayer() == pcbnew.In1_Cu
    ]
    if in1_tracks:
        raise SystemExit(f"In1 must be plane-only; found {len(in1_tracks)} tracks")
    in1_zones = [
        zone
        for zone in board.Zones()
        if not zone.GetIsRuleArea() and zone.GetLayer() == pcbnew.In1_Cu
    ]
    if len(in1_zones) != 1 or in1_zones[0].GetNetname() != "/GND":
        raise SystemExit("In1 must contain exactly one /GND zone")
    if in1_zones[0].GetPadConnection() != pcbnew.ZONE_CONNECTION_FULL:
        raise SystemExit("In1 /GND plane must use solid pad connections")
    filled = in1_zones[0].GetFilledPolysList(pcbnew.In1_Cu)
    if filled.OutlineCount() != 1:
        raise SystemExit("In1 /GND plane must be one continuous filled outline")
    main = filled.COutline(0)
    if main.Area() < 3_000 * pcbnew.FromMM(1.0) ** 2:
        raise SystemExit("In1 main /GND filled outline is unexpectedly small")
    # Sample open copper in every board quadrant plus the load-entry region.
    # Pad centres themselves can be excluded from a zone polygon by thermal
    # relief geometry, so they are intentionally not used as fill checkpoints.
    checkpoints = (
        (2.0, 10.0),
        (10.0, 10.0),
        (55.0, 10.0),
        (30.0, 30.0),
        (55.0, 30.0),
        (10.0, 50.0),
        (30.0, 50.0),
        (50.0, 50.0),
    )
    if not all(filled.Contains(pcbnew.VECTOR2I_MM(*point)) for point in checkpoints):
        raise SystemExit("In1 main /GND plane does not span all required checkpoints")

    all_vias = [item for item in board.GetTracks() if isinstance(item, pcbnew.PCB_VIA)]
    if len(all_vias) != 75:
        raise SystemExit(
            f"Expected 75 ordinary vias after stitching; found {len(all_vias)}"
        )
    if any(item.GetViaType() != pcbnew.VIATYPE_THROUGH for item in all_vias):
        raise SystemExit("A blind, buried, or microvia remains on B1")
    gnd_code = board.GetNetcodeFromNetname("/GND")
    for x_mm, y_mm in GND_STITCHING_VIAS_MM:
        expected = pcbnew.VECTOR2I_MM(x_mm, y_mm)
        matches = [
            item
            for item in all_vias
            if item.GetNetCode() == gnd_code
            and item.GetPosition().x == expected.x
            and item.GetPosition().y == expected.y
        ]
        if len(matches) != 1:
            raise SystemExit(f"Missing unique GND stitching via at {(x_mm, y_mm)}")
        via = matches[0]
        if (
            pcbnew.ToMM(via.GetWidth(pcbnew.F_Cu)) < 0.60
            or pcbnew.ToMM(via.GetDrill()) < 0.30
        ):
            raise SystemExit(f"Undersized GND stitching via at {(x_mm, y_mm)}")

    details: dict[str, object] = {}
    for netname, minimum in WIDTHS.items():
        code = board.GetNetcodeFromNetname(netname)
        inner = [
            item
            for item in board.GetTracks()
            if type(item) is pcbnew.PCB_TRACK
            and item.GetNetCode() == code
            and item.GetLayer() == pcbnew.In2_Cu
        ]
        invalid_inner = [
            item
            for item in board.GetTracks()
            if type(item) is pcbnew.PCB_TRACK
            and item.GetNetCode() == code
            and item.GetLayer() not in (pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
        ]
        vias = [
            item
            for item in board.GetTracks()
            if isinstance(item, pcbnew.PCB_VIA) and item.GetNetCode() == code
        ]
        if not inner or min(pcbnew.ToMM(item.GetWidth()) for item in inner) < minimum:
            raise SystemExit(f"{netname} width contract failed")
        if invalid_inner:
            raise SystemExit(f"{netname} escaped onto an invalid routing layer")
        if len(vias) != VIA_COUNTS[netname]:
            raise SystemExit(f"{netname} supply via count drift")
        for via in vias:
            if via.GetViaType() != pcbnew.VIATYPE_THROUGH:
                raise SystemExit(f"{netname} contains a non-through via")
            if (
                pcbnew.ToMM(via.GetWidth(pcbnew.F_Cu)) < 0.60
                or pcbnew.ToMM(via.GetDrill()) < 0.30
            ):
                raise SystemExit(f"{netname} contains an undersized via")
        details[netname] = {
            "minimum_in2_width_mm": min(pcbnew.ToMM(item.GetWidth()) for item in inner),
            "ordinary_through_vias": len(vias),
        }

    allowed_in2 = {"/3V3", "/EPD_3V3", "/V_B"}
    other_in2 = sorted(
        {
            item.GetNetname()
            for item in board.GetTracks()
            if type(item) is pcbnew.PCB_TRACK
            and item.GetLayer() == pcbnew.In2_Cu
            and item.GetNetname() not in allowed_in2
        }
    )
    if other_in2:
        raise SystemExit(f"Unexpected non-supply routing on In2: {other_in2}")

    for switch in ("/SW_H", "/SW_C"):
        code = board.GetNetcodeFromNetname(switch)
        invalid = [
            item
            for item in board.GetTracks()
            if item.GetNetCode() == code
            and (isinstance(item, pcbnew.PCB_VIA) or item.GetLayer() != pcbnew.F_Cu)
        ]
        if invalid:
            raise SystemExit(f"{switch} left F.Cu or contains a via")

    j2 = board.FindFootprintByReference("J2")
    for number in ("1", "2"):
        pad = j2.FindPadByNumber(number) if j2 is not None else None
        if (
            pad is None
            or not pad.GetNetname().startswith("unconnected-(J2-")
            or not pad.GetNetname().endswith(f"-Pad{number})")
        ):
            raise SystemExit(f"J2:{number} is not its private NC net")
        if any(item.GetNetCode() == pad.GetNetCode() for item in board.GetTracks()):
            raise SystemExit(f"J2:{number} private NC net has copper routing")

    r15 = board.FindFootprintByReference("R15")
    r16 = board.FindFootprintByReference("R16")
    if r15 is None or not r15.IsDNP() or r16 is None or r16.IsDNP():
        raise SystemExit("Population contract drift: R16 FIT / R15 DNP required")

    required_layers = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
    rule_areas = [zone for zone in board.Zones() if zone.GetIsRuleArea()]
    if len(rule_areas) != 5 or not all(
        all(zone.GetLayerSet().Contains(layer) for layer in required_layers)
        for zone in rule_areas
    ):
        raise SystemExit("Antenna/edge keepouts must cover all four copper layers")

    return {
        "copper_layers": 4,
        "paste_layers_enabled": ["F.Paste", "B.Paste"],
        "in1_tracks": 0,
        "in1_gnd_filled_outlines": filled.OutlineCount(),
        "in1_main_gnd_area_mm2": main.Area() / pcbnew.FromMM(1.0) ** 2,
        "in1_gnd_pad_connection": "solid",
        "in2_only_supply_routing": True,
        "blind_buried_microvias": 0,
        "total_ordinary_through_vias": len(all_vias),
        "added_gnd_stitching_vias": [
            {"x_mm": x_mm, "y_mm": y_mm} for x_mm, y_mm in GND_STITCHING_VIAS_MM
        ],
        "switch_nodes_f_cu_only": True,
        "all_rule_areas_cover_four_copper_layers": True,
        "supplies": details,
    }


def write_manifest(paths: list[Path], audit: dict[str, object]) -> Path:
    manifest = OUT / "verification_manifest.json"
    data = {
        "schema": 1,
        "project": PROJECT,
        "revision": "B1-4L-ENG",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "release_class": "ENGINEERING_CANDIDATE_NOT_PRODUCTION_RELEASE",
        "checks": {
            "erc_errors": 0,
            "erc_warnings": 0,
            "drc_violations": 0,
            "unconnected_pads": 0,
            "schematic_parity_errors": 0,
        },
        "board_audit": audit,
        "known_limits": [
            "R4.1 uses a 0.50 mm short local In2 neck before the 0.60 mm /3V3 bus.",
            "Four-layer stack-up, copper thickness, and impedance are not fabricator-qualified.",
            "J2 socket MPN/drill fit, actual N16R8 Z-envelope, FPC and J3 mechanics remain open.",
            "Seven GPIOs cross USB/panel power domains without Ioff isolation.",
            "No Gerber/drill manufacturing package is released.",
        ],
        "artifacts": {
            path.relative_to(OUT).as_posix(): {
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in paths
        },
    }
    manifest.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    if list(OUT.glob("~*.lck")):
        raise SystemExit("Close KiCad before verifying B1")
    prep.configure_modules()
    prep.route.OUT = OUT
    prep.route.PROJECT = PROJECT
    prep.route.BOARD_PATH = BOARD
    prep.route.SCH_PATH = SCHEMATIC

    refill_gate = OUT / "drc_refill_gate.rpt"
    run(
        "pcb",
        "drc",
        "--exit-code-violations",
        "--severity-all",
        "--schematic-parity",
        "--refill-zones",
        "--save-board",
        "-o",
        str(refill_gate),
        str(BOARD),
    )
    refill_text = refill_gate.read_text(encoding="utf-8")
    require(r"\*\* Found 0 DRC violations \*\*", refill_text, "refill-gate DRC")
    require(
        r"\*\* Found 0 unconnected pads \*\*", refill_text, "refill-gate connection"
    )
    require(r"\*\* Found 0 Footprint errors \*\*", refill_text, "refill-gate parity")

    board = pcbnew.LoadBoard(str(BOARD))
    if board is None:
        raise SystemExit(f"Cannot load {BOARD}")
    prep.route.verify_board_pin_nets(board)
    prep.route.verify_reference_component_pinouts(board)
    board_audit = audit_board(board)
    design_audit_path = OUT / "design_audit.json"
    design_audit = json.loads(design_audit_path.read_text(encoding="utf-8"))
    if design_audit.get("board_sha256") != sha256(BOARD):
        raise SystemExit("design_audit.json does not bind the final PCB")
    netlist = prep.route.verify_schematic_netlist()

    erc = OUT / "erc_final.rpt"
    drc = OUT / "drc_final.rpt"
    preview = OUT / "preview"
    preview.mkdir(exist_ok=True)
    run("sch", "erc", "--exit-code-violations", "-o", str(erc), str(SCHEMATIC))
    run(
        "pcb",
        "drc",
        "--exit-code-violations",
        "--severity-all",
        "--schematic-parity",
        "-o",
        str(drc),
        str(BOARD),
    )
    prep.route.require_erc_clean(erc)
    text = drc.read_text(encoding="utf-8")
    require(r"\*\* Found 0 DRC violations \*\*", text, "DRC")
    require(r"\*\* Found 0 unconnected pads \*\*", text, "connection")
    require(r"\*\* Found 0 Footprint errors \*\*", text, "parity")
    for side in ("top", "bottom"):
        run(
            "pcb",
            "render",
            "-o",
            str(preview / f"final_{side}.png"),
            "--side",
            side,
            "--background",
            "opaque",
            "--quality",
            "high",
            "--width",
            "1800",
            "--height",
            "1600",
            str(BOARD),
        )
    manifest = write_manifest(
        [
            BOARD,
            SCHEMATIC,
            OUT / f"{PROJECT}.kicad_pro",
            netlist,
            erc,
            drc,
            refill_gate,
            design_audit_path,
            OUT / "README.md",
            preview / "final_top.png",
            preview / "final_bottom.png",
        ],
        board_audit,
    )
    print(f"PASS board={BOARD} manifest={manifest}")


if __name__ == "__main__":
    main()
