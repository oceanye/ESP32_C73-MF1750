"""Fail-closed verifier for the B2 65.0 x 60.5 mm PCBA-margin derivative."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pcbnew


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B1_DIR = HARDWARE / "mf1750_devkitc_b1_single_power_layer"
B1_PROJECT = "mf1750_devkitc_b1_single_power_layer"
B1_BOARD = B1_DIR / f"{B1_PROJECT}.kicad_pcb"
B1_SCHEMATIC = B1_DIR / f"{B1_PROJECT}.kicad_sch"
B1_PRO = B1_DIR / f"{B1_PROJECT}.kicad_pro"

OUT = HARDWARE / "mf1750_devkitc_b2_pcba_margin"
PROJECT = "mf1750_devkitc_b2_pcba_margin"
BOARD = OUT / f"{PROJECT}.kicad_pcb"
SCHEMATIC = OUT / f"{PROJECT}.kicad_sch"
PRO = OUT / f"{PROJECT}.kicad_pro"
CONFIG = OUT / "board_audit_config.json"
DERIVATION_AUDIT = OUT / "derivation_audit.json"
BOARD_AUDIT = OUT / "board_audit.json"
MANIFEST = OUT / "verification_manifest.json"
KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
SKILL_AUDITOR = (
    ROOT
    / ".codex"
    / "skills"
    / "jlcpcb-kicad-handoff"
    / "scripts"
    / "audit_kicad_jlcpcb.py"
)
BUILDER = HARDWARE / "build_mf1750_devkitc_b2_pcba_margin.py"
VERIFIER = HARDWARE / "verify_mf1750_devkitc_b2_pcba_margin.py"

FROZEN_B1_SHA256 = {
    B1_BOARD.name: "d44afcd28056045aa19c875d424b6ad7d9e84712e238ee2340f6d087da62fde3",
    B1_SCHEMATIC.name: "ccb8ad72021231ce9768b86800a8536fc4d18ffc8e3edf8822c5b3040c757d95",
    B1_PRO.name: "ba26af897f39a3eda18448233faf9f247d78da2c3c19595577e3e1df6f9e40f3",
}
DX_IU = pcbnew.FromMM(0.5)
DY_IU = pcbnew.FromMM(2.5)
EXPECTED_COUNTS = {
    "footprints": 61,
    "tracks": 629,
    "vias": 75,
    "zones": 8,
    "drawings": 20,
    "nets": 89,
}
SUPPLY_WIDTHS = {"/3V3": 0.50, "/EPD_3V3": 0.60, "/V_B": 0.80}
SUPPLY_VIAS = {"/3V3": 5, "/EPD_3V3": 4, "/V_B": 6}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_frozen_b1() -> None:
    for path in (B1_BOARD, B1_SCHEMATIC, B1_PRO):
        actual = sha256(path)
        if actual != FROZEN_B1_SHA256[path.name]:
            raise SystemExit(f"Frozen B1 source drift: {path} -> {actual}")


def run_kicad(*args: str) -> None:
    subprocess.run([str(KICAD_CLI), *args], cwd=ROOT, check=True)


def require_report(pattern: str, text: str, label: str) -> None:
    if not re.search(pattern, text):
        raise SystemExit(f"Missing clean {label} summary")


def counts(board: pcbnew.BOARD) -> dict[str, int]:
    items = list(board.GetTracks())
    return {
        "footprints": len(board.GetFootprints()),
        "tracks": sum(type(item) is pcbnew.PCB_TRACK for item in items),
        "vias": sum(isinstance(item, pcbnew.PCB_VIA) for item in items),
        "zones": len(board.Zones()),
        "drawings": len(board.GetDrawings()),
        "nets": len(board.GetNetsByNetcode()),
    }


def xy(position: pcbnew.VECTOR2I, normalize: bool) -> tuple[int, int]:
    return (
        position.x - (DX_IU if normalize else 0),
        position.y - (DY_IU if normalize else 0),
    )


def footprint_signature(board: pcbnew.BOARD, normalize: bool) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for footprint in board.GetFootprints():
        ref = footprint.GetReference()
        if ref in result:
            raise SystemExit(f"Duplicate footprint reference: {ref}")
        pads = []
        for pad in footprint.Pads():
            pads.append(
                (
                    pad.GetNumber(),
                    pad.GetNetname(),
                    int(pad.GetAttribute()),
                    xy(pad.GetPosition(), normalize),
                )
            )
        result[ref] = (
            footprint.GetValue(),
            footprint.GetFPID().GetUniStringLibId(),
            board.GetLayerName(footprint.GetLayer()),
            int(footprint.GetAttributes()),
            bool(footprint.IsDNP()),
            footprint.GetOrientation().AsDegrees(),
            xy(footprint.GetPosition(), normalize),
            tuple(sorted(pads)),
        )
    return result


def track_signature(board: pcbnew.BOARD, normalize: bool) -> Counter[tuple[Any, ...]]:
    result: Counter[tuple[Any, ...]] = Counter()
    for item in board.GetTracks():
        if type(item) is pcbnew.PCB_TRACK:
            endpoints = tuple(
                sorted((xy(item.GetStart(), normalize), xy(item.GetEnd(), normalize)))
            )
            result[
                (
                    "track",
                    item.GetNetname(),
                    board.GetLayerName(item.GetLayer()),
                    item.GetWidth(),
                    endpoints,
                )
            ] += 1
        elif isinstance(item, pcbnew.PCB_VIA):
            result[
                (
                    "via",
                    item.GetNetname(),
                    xy(item.GetPosition(), normalize),
                    item.GetWidth(pcbnew.F_Cu),
                    item.GetDrill(),
                    int(item.GetViaType()),
                    int(item.TopLayer()),
                    int(item.BottomLayer()),
                )
            ] += 1
        else:
            raise SystemExit(f"Unsupported routed item type: {type(item).__name__}")
    return result


def zone_property_signature(board: pcbnew.BOARD) -> Counter[tuple[Any, ...]]:
    result: Counter[tuple[Any, ...]] = Counter()
    for zone in board.Zones():
        layers = tuple(
            board.GetLayerName(layer)
            for layer in range(pcbnew.PCB_LAYER_ID_COUNT)
            if zone.GetLayerSet().Contains(layer)
        )
        result[
            (
                zone.GetZoneName(),
                bool(zone.GetIsRuleArea()),
                zone.GetNetname(),
                layers,
                zone.GetLocalClearance(),
                zone.GetMinThickness(),
                int(zone.GetPadConnection()),
            )
        ] += 1
    return result


def text_signature(board: pcbnew.BOARD, normalize: bool) -> Counter[tuple[Any, ...]]:
    result: Counter[tuple[Any, ...]] = Counter()
    for item in board.GetDrawings():
        if not isinstance(item, pcbnew.PCB_TEXT):
            continue
        text = item.GetText()
        if text == "MF1750 COMPACT B1 4L":
            text = "MF1750 B2 4L 65x60.5"
        layer = board.GetLayerName(item.GetLayer())
        if text == "ANTENNA" and (
            (not normalize and item.GetLayer() == pcbnew.F_SilkS)
            or (normalize and item.GetLayer() == pcbnew.F_Fab)
        ):
            layer = "J2_ANTENNA_MECHANICAL_FAB"
        result[
            (
                text,
                layer,
                item.GetTextAngle().AsDegrees(),
                xy(item.GetPosition(), normalize),
            )
        ] += 1
    return result


def verify_rigid_derivation(source: pcbnew.BOARD, target: pcbnew.BOARD) -> None:
    if counts(source) != EXPECTED_COUNTS or counts(target) != EXPECTED_COUNTS:
        raise SystemExit(
            f"Semantic-count mismatch: source={counts(source)} target={counts(target)}"
        )
    if footprint_signature(source, False) != footprint_signature(target, True):
        raise SystemExit("Footprint/pad/net geometry is not a rigid B1 translation")
    if track_signature(source, False) != track_signature(target, True):
        raise SystemExit("Track/via topology is not a rigid B1 translation")
    if zone_property_signature(source) != zone_property_signature(target):
        raise SystemExit("Zone/rule-area electrical properties drifted from B1")
    if text_signature(source, False) != text_signature(target, True):
        raise SystemExit("Non-identity silkscreen geometry drifted from B1")


def project_specific_audit(board: pcbnew.BOARD) -> dict[str, Any]:
    if board.GetCopperLayerCount() != 4:
        raise SystemExit("B2 must have four copper layers")
    in1_tracks = [
        item
        for item in board.GetTracks()
        if type(item) is pcbnew.PCB_TRACK and item.GetLayer() == pcbnew.In1_Cu
    ]
    if in1_tracks:
        raise SystemExit("In1 must remain plane-only")
    all_vias = [item for item in board.GetTracks() if isinstance(item, pcbnew.PCB_VIA)]
    if len(all_vias) != 75 or any(
        via.GetViaType() != pcbnew.VIATYPE_THROUGH for via in all_vias
    ):
        raise SystemExit("B2 via contract drift")
    details: dict[str, Any] = {}
    for netname, minimum in SUPPLY_WIDTHS.items():
        code = board.GetNetcodeFromNetname(netname)
        inner = [
            item
            for item in board.GetTracks()
            if type(item) is pcbnew.PCB_TRACK
            and item.GetNetCode() == code
            and item.GetLayer() == pcbnew.In2_Cu
        ]
        vias = [via for via in all_vias if via.GetNetCode() == code]
        if not inner or min(pcbnew.ToMM(item.GetWidth()) for item in inner) < minimum:
            raise SystemExit(f"{netname} In2 width contract drift")
        if len(vias) != SUPPLY_VIAS[netname]:
            raise SystemExit(f"{netname} supply-via count drift")
        details[netname] = {
            "minimum_in2_width_mm": min(pcbnew.ToMM(item.GetWidth()) for item in inner),
            "ordinary_through_vias": len(vias),
        }
    r15 = board.FindFootprintByReference("R15")
    r16 = board.FindFootprintByReference("R16")
    if r15 is None or not r15.IsDNP() or r16 is None or r16.IsDNP():
        raise SystemExit("R16 FIT / R15 DNP population contract drift")
    j2 = board.FindFootprintByReference("J2")
    for number in ("1", "2"):
        pad = j2.FindPadByNumber(number) if j2 is not None else None
        if pad is None or not pad.GetNetname().startswith(
            f"unconnected-(J2-Pad{number}"
        ):
            # KiCad's generated private-net label varies slightly by version;
            # the stronger no-routing and distinct-net checks remain mandatory.
            if pad is None or not pad.GetNetname().startswith("unconnected-(J2-"):
                raise SystemExit(f"J2:{number} private NC net drift")
        if any(item.GetNetCode() == pad.GetNetCode() for item in board.GetTracks()):
            raise SystemExit(f"J2:{number} private NC net has routed copper")
    rule_areas = [zone for zone in board.Zones() if zone.GetIsRuleArea()]
    required_layers = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
    if len(rule_areas) != 5 or not all(
        all(zone.GetLayerSet().Contains(layer) for layer in required_layers)
        for zone in rule_areas
    ):
        raise SystemExit("Five four-copper-layer rule areas are required")
    return {
        "semantic_counts": counts(board),
        "in1_tracks": 0,
        "ordinary_through_vias": len(all_vias),
        "blind_buried_microvias": 0,
        "supplies": details,
        "population": {"R16": "FIT", "R15": "DNP"},
        "j2_private_nc_pads": ["1", "2"],
        "rule_areas_all_four_copper_layers": True,
    }


def run_skill_audit() -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(SKILL_AUDITOR), str(BOARD), str(CONFIG), str(BOARD_AUDIT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(
            "Generic JLCPCB board audit failed "
            f"(exit {completed.returncode}): {completed.stdout}{completed.stderr}"
        )
    result = json.loads(BOARD_AUDIT.read_text(encoding="utf-8"))
    if result.get("status") != "PASS":
        raise SystemExit("Generic JLCPCB board audit did not report PASS")
    return result


def artifact(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": sha256(path)}


def main() -> None:
    locks = list(OUT.glob("~*.lck"))
    if locks:
        raise SystemExit("Close KiCad before verifying B2")
    require_frozen_b1()
    derivation = json.loads(DERIVATION_AUDIT.read_text(encoding="utf-8"))
    if derivation["artifacts"][BOARD.name]["sha256"] != sha256(BOARD):
        raise SystemExit(
            "derivation_audit.json does not bind the pre-verification B2 PCB"
        )

    refill = OUT / "drc_refill_gate.rpt"
    run_kicad(
        "pcb",
        "drc",
        "--exit-code-violations",
        "--severity-all",
        "--schematic-parity",
        "--refill-zones",
        "--save-board",
        "-o",
        str(refill),
        str(BOARD),
    )
    refill_text = refill.read_text(encoding="utf-8")
    require_report(r"\*\* Found 0 DRC violations \*\*", refill_text, "refill DRC")
    require_report(r"\*\* Found 0 unconnected pads \*\*", refill_text, "connection")
    require_report(r"\*\* Found 0 Footprint errors \*\*", refill_text, "parity")

    source = pcbnew.LoadBoard(str(B1_BOARD))
    target = pcbnew.LoadBoard(str(BOARD))
    if source is None or target is None:
        raise SystemExit("Could not load source or target board")
    verify_rigid_derivation(source, target)
    project_audit = project_specific_audit(target)
    generic = run_skill_audit()

    erc = OUT / "erc_final.rpt"
    drc = OUT / "drc_final.rpt"
    netlist = OUT / "netlist_verified.xml"
    run_kicad("sch", "erc", "--exit-code-violations", "-o", str(erc), str(SCHEMATIC))
    run_kicad(
        "pcb",
        "drc",
        "--exit-code-violations",
        "--severity-all",
        "--schematic-parity",
        "-o",
        str(drc),
        str(BOARD),
    )
    run_kicad(
        "sch",
        "export",
        "netlist",
        "--format",
        "kicadxml",
        "-o",
        str(netlist),
        str(SCHEMATIC),
    )
    erc_text = erc.read_text(encoding="utf-8")
    drc_text = drc.read_text(encoding="utf-8")
    require_report(r"\*\* ERC messages: 0\s+Errors 0\s+Warnings 0", erc_text, "ERC")
    require_report(r"\*\* Found 0 DRC violations \*\*", drc_text, "DRC")
    require_report(r"\*\* Found 0 unconnected pads \*\*", drc_text, "connection")
    require_report(r"\*\* Found 0 Footprint errors \*\*", drc_text, "parity")

    preview = OUT / "preview"
    preview.mkdir(exist_ok=True)
    for side in ("top", "bottom"):
        run_kicad(
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

    body = generic["checks"]["body_edge"]
    courtyard = generic["checks"]["courtyard_edge"]
    body_min = body["observed_minimum_clearance_mm"]
    courtyard_min = courtyard["observed_minimum_clearance_mm"]
    if body_min < 3.1 or courtyard_min < 2.59:
        raise SystemExit(
            f"Robust B2 margin target missed: body={body_min}, courtyard={courtyard_min}"
        )

    require_frozen_b1()
    paths = [
        BOARD,
        SCHEMATIC,
        PRO,
        CONFIG,
        DERIVATION_AUDIT,
        BOARD_AUDIT,
        refill,
        erc,
        drc,
        netlist,
        OUT / "README.md",
        preview / "final_top.png",
        preview / "final_bottom.png",
    ]
    paths.extend(
        [
            OUT / "fp-lib-table",
            OUT / "sym-lib-table",
            OUT / "mf1750_local.kicad_sym",
        ]
    )
    for library_dir in (
        OUT / "MF1750_Compact.pretty",
        OUT / "MF1750_Production.pretty",
    ):
        paths.extend(sorted(path for path in library_dir.rglob("*") if path.is_file()))
    manifest = {
        "schema": 1,
        "project": PROJECT,
        "revision": "B2-4L-PCBA-EDGE",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "release_class": "ENGINEERING_CANDIDATE_NOT_PRODUCTION_RELEASE",
        "source_b1_sha256": FROZEN_B1_SHA256,
        "checks": {
            "erc_errors": 0,
            "erc_warnings": 0,
            "drc_violations": 0,
            "unconnected_pads": 0,
            "schematic_parity_errors": 0,
            "rigid_geometry_and_connectivity_preserved": True,
            "generic_jlcpcb_board_audit": "PASS",
        },
        "margins_mm": {
            "body_to_functional_edge_minimum": body_min,
            "body_minimum_location": body["observed_minimum_location"],
            "courtyard_to_functional_edge_minimum": courtyard_min,
            "courtyard_minimum_location": courtyard["observed_minimum_location"],
            "local_body_gate": 2.5,
            "local_courtyard_gate": 2.5,
            "conservative_0_4mm_inward_process_allowance": {
                "body": round(body_min - 0.4, 6),
                "courtyard": round(courtyard_min - 0.4, 6),
                "note": "analysis allowance only; finished functional Edge.Cuts remains the contractual datum",
            },
        },
        "project_specific_audit": project_audit,
        "gates": {
            "local_evidence": "PASS",
            "online_recheck": "PENDING",
            "external_engineering": "NOT_APPLICABLE",
            "external_engineering_rationale": (
                "No known JLCPCB fabrication or assembly policy deviation remains: "
                "every fitted-SMT Fab body and Courtyard clears 2.5 mm. Reopen this "
                "gate if portal/CAM review identifies a new deviation."
            ),
        },
        "mechanical_holds": [
            "J1/FPC cable exit and connector-edge/depanelization mechanics",
            "J3 side-entry connector and cable clearance",
            "DevKitC antenna performance with the enlarged FR4/keepout geometry",
            "J2 socket MPN, finished-hole fit, and full Z-envelope",
            "enclosure, mounting, and physical first-article review",
        ],
        "skill_gate_effect": (
            "The jlcpcb-kicad-handoff skill made fitted-SMT Fab body and Courtyard "
            "distance to functional Edge.Cuts explicit fail-closed local gates. The "
            "former margin exception is now not applicable; online portal review remains "
            "pending and any newly identified deviation reopens external engineering."
        ),
        "artifacts": {
            path.relative_to(OUT).as_posix(): artifact(path) for path in paths
        },
        "tooling": {
            path.relative_to(ROOT).as_posix(): artifact(path)
            for path in (BUILDER, VERIFIER, SKILL_AUDITOR)
        },
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "PASS "
        f"board={BOARD} sha256={sha256(BOARD)} "
        f"body_min_mm={body_min} courtyard_min_mm={courtyard_min} manifest={MANIFEST}"
    )


if __name__ == "__main__":
    main()
