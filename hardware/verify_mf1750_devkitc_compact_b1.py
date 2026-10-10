"""Fail-closed verification for the four-layer ordinary-via Rev B1 probe."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
OUT = HARDWARE / "mf1750_devkitc_compact_b1"
PROJECT = "mf1750_devkitc_compact_b1"
KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")

sys.path.insert(0, str(HARDWARE))
import prepare_mf1750_devkitc_compact_freerouting as prep  # noqa: E402


SUPPLY_CONTRACT = {
    "/3V3": ("In1.Cu", 0.50, 5),
    "/EPD_3V3": ("In2.Cu", 0.60, 4),
    "/V_B": ("In2.Cu", 0.80, 6),
}


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


def audit_board(board) -> dict[str, object]:
    pcbnew = prep.route.pcbnew
    if board.GetCopperLayerCount() != 4:
        raise SystemExit(
            f"B1 requires 4 copper layers, got {board.GetCopperLayerCount()}"
        )

    details: dict[str, object] = {}
    for net, (layer_name, minimum_width, expected_vias) in SUPPLY_CONTRACT.items():
        layer = board.GetLayerID(layer_name)
        code = board.GetNetcodeFromNetname(net)
        tracks = [
            item
            for item in board.GetTracks()
            if type(item) is pcbnew.PCB_TRACK
            and item.GetNetCode() == code
            and item.GetLayer() == layer
        ]
        vias = [
            item
            for item in board.GetTracks()
            if isinstance(item, pcbnew.PCB_VIA) and item.GetNetCode() == code
        ]
        if not tracks:
            raise SystemExit(f"{net} has no routing on {layer_name}")
        widths = [pcbnew.ToMM(item.GetWidth()) for item in tracks]
        if min(widths) + 1e-9 < minimum_width:
            raise SystemExit(f"{net} has a neck below {minimum_width:.2f} mm")
        if len(vias) != expected_vias:
            raise SystemExit(f"{net}: expected {expected_vias} vias, found {len(vias)}")
        for via in vias:
            if via.GetViaType() != pcbnew.VIATYPE_THROUGH:
                raise SystemExit(f"{net} contains a blind/buried/microvia")
            if pcbnew.ToMM(via.GetWidth()) < 0.60 or pcbnew.ToMM(via.GetDrill()) < 0.30:
                raise SystemExit(f"{net} contains an undersized supply via")
        details[net] = {
            "layer": layer_name,
            "minimum_width_mm": min(widths),
            "ordinary_through_vias": len(vias),
        }

    for switch_net in ("/SW_H", "/SW_C"):
        code = board.GetNetcodeFromNetname(switch_net)
        invalid = [
            item
            for item in board.GetTracks()
            if item.GetNetCode() == code
            and (isinstance(item, pcbnew.PCB_VIA) or item.GetLayer() != pcbnew.F_Cu)
        ]
        if invalid:
            raise SystemExit(f"{switch_net} left F.Cu or contains a via")

    j2 = board.FindFootprintByReference("J2")
    for number in ("1", "2"):
        pad = j2.FindPadByNumber(number) if j2 is not None else None
        if (
            pad is None
            or not pad.GetNetname().startswith("unconnected-(J2-")
            or not pad.GetNetname().endswith(f"-Pad{number})")
        ):
            raise SystemExit(f"J2:{number} must remain a private NC pad")
        if pad.GetNetCode() and any(
            item.GetNetCode() == pad.GetNetCode() for item in board.GetTracks()
        ):
            raise SystemExit(f"J2:{number} NC net has routing")

    r15 = board.FindFootprintByReference("R15")
    r16 = board.FindFootprintByReference("R16")
    if r15 is None or not r15.IsDNP() or r16 is None or r16.IsDNP():
        raise SystemExit("Population contract drift: R16 FIT / R15 DNP required")

    keepouts = [
        zone
        for zone in board.Zones()
        if zone.GetIsRuleArea() and zone.GetZoneName() == "DEVKITC_ANTENNA_KEEP_OUT"
    ]
    if len(keepouts) != 1:
        raise SystemExit("Expected one DEVKITC_ANTENNA_KEEP_OUT")
    required_layers = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
    layer_set = keepouts[0].GetLayerSet()
    if not all(layer_set.Contains(layer) for layer in required_layers):
        raise SystemExit("Antenna rule area does not cover all four copper layers")
    box = (60.10, 31.60, 62.00, 57.35)
    for item in board.GetTracks():
        points = (
            (item.GetStart(), item.GetEnd())
            if type(item) is pcbnew.PCB_TRACK
            else (item.GetPosition(),)
        )
        if any(
            box[0] <= pcbnew.ToMM(point.x) <= box[2]
            and box[1] <= pcbnew.ToMM(point.y) <= box[3]
            for point in points
        ):
            raise SystemExit("Track/via enters the antenna keepout rectangle")

    return {
        "copper_layers": 4,
        "blind_buried_microvias": 0,
        "switch_nodes_f_cu_only": True,
        "antenna_keepout_all_copper_layers": True,
        "supplies": details,
    }


def write_manifest(paths: list[Path], board_audit: dict[str, object]) -> Path:
    manifest_path = OUT / "verification_manifest.json"
    artifacts = {
        path.relative_to(OUT).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in paths
    }
    data = {
        "schema": 1,
        "project": PROJECT,
        "revision": "B1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "release_class": "ENGINEERING_REVIEW_PROBE_NOT_PRODUCTION_RELEASE",
        "checks": {
            "erc_errors": 0,
            "erc_warnings": 0,
            "drc_violations": 0,
            "unconnected_pads": 0,
            "schematic_parity_errors": 0,
        },
        "board_audit": board_audit,
        "known_limits": [
            "The current routed probe splits power between In1 and In2; an uninterrupted dedicated GND plane is not yet implemented.",
            "R4 input has one 0.50 mm local internal dog-bone neck before the 0.60 mm /3V3 distribution.",
            "No fabricator-qualified four-layer stack-up, copper thickness, or impedance specification is frozen.",
            "J2 socket MPN, drill fit, N16R8 Z-envelope, and GPIO Ioff isolation remain open.",
            "No Gerber/drill manufacturing package is released.",
        ],
        "artifacts": artifacts,
    }
    manifest_path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest_path


def main() -> None:
    locks = sorted(OUT.glob("~*.lck"))
    if locks:
        raise SystemExit(
            "Close KiCad before B1 verification: " + ", ".join(p.name for p in locks)
        )
    prep.configure_modules()
    prep.route.OUT = OUT
    prep.route.PROJECT = PROJECT
    prep.route.BOARD_PATH = OUT / f"{PROJECT}.kicad_pcb"
    prep.route.SCH_PATH = OUT / f"{PROJECT}.kicad_sch"
    board_path = prep.route.BOARD_PATH
    schematic_path = prep.route.SCH_PATH
    board = prep.route.pcbnew.LoadBoard(str(board_path))
    if board is None:
        raise SystemExit(f"Cannot load {board_path}")
    prep.route.verify_board_pin_nets(board)
    prep.route.verify_reference_component_pinouts(board)
    board_audit = audit_board(board)
    netlist = prep.route.verify_schematic_netlist()

    erc = OUT / "erc_final.rpt"
    drc = OUT / "drc_final.rpt"
    preview = OUT / "preview"
    preview.mkdir(exist_ok=True)
    run("sch", "erc", "--exit-code-violations", "-o", str(erc), str(schematic_path))
    run(
        "pcb",
        "drc",
        "--exit-code-violations",
        "--severity-all",
        "--schematic-parity",
        "--refill-zones",
        "--save-board",
        "-o",
        str(drc),
        str(board_path),
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
            str(board_path),
        )
    manifest = write_manifest(
        [
            board_path,
            schematic_path,
            OUT / f"{PROJECT}.kicad_pro",
            OUT / "bom_reference.csv",
            netlist,
            erc,
            drc,
            preview / "final_top.png",
            preview / "final_bottom.png",
        ],
        board_audit,
    )
    print(f"PASS board={board_path} manifest={manifest}")


if __name__ == "__main__":
    main()
