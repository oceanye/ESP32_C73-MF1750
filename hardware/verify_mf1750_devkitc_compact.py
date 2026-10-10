"""Verify and render the authoritative compact MF-1750 Rev B0 design."""

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
OUT = HARDWARE / "mf1750_devkitc_compact"
PROJECT = "mf1750_devkitc_compact"
KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")

sys.path.insert(0, str(HARDWARE))
import prepare_mf1750_devkitc_compact_freerouting as prep  # noqa: E402


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


def write_manifest(paths: list[Path]) -> Path:
    """Bind the authoritative B0 handoff without blessing stale work files."""
    manifest_path = OUT / "verification_manifest.json"
    artifacts = {}
    for path in paths:
        if not path.is_file():
            raise SystemExit(f"Missing canonical artifact: {path}")
        artifacts[path.relative_to(OUT).as_posix()] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    manifest = {
        "schema": 1,
        "project": PROJECT,
        "revision": "B0",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "release_class": "ENGINEERING_PROTOTYPE_NOT_PRODUCTION_RELEASE",
        "checks": {
            "erc_errors": 0,
            "erc_warnings": 0,
            "drc_violations": 0,
            "unconnected_pads": 0,
            "schematic_parity_errors": 0,
        },
        "known_limits": [
            "Two-layer supply distribution retains 0.20 mm necks on /3V3, /EPD_3V3, and /V_B.",
            "The local /3V3 relief is partial/discontinuous, not a continuous J3-to-R4/R8 copper bus.",
            "J2 socket MPN, finished-hole fit, and the actual N16R8 Z-envelope are not yet qualified.",
            "Seven GPIOs cross the USB/panel power domains without Ioff isolation.",
            "No Gerber/drill manufacturing package is released from this directory.",
        ],
        "artifacts": artifacts,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest_path


def reject_open_project_lock() -> None:
    locks = sorted(OUT.glob("~*.lck"))
    if locks:
        joined = ", ".join(path.name for path in locks)
        raise SystemExit(
            "Project lock file present; close KiCad before final verification: "
            + joined
        )


def main() -> None:
    reject_open_project_lock()
    prep.configure_modules()
    route = prep.route
    board_path = OUT / f"{PROJECT}.kicad_pcb"
    schematic_path = OUT / f"{PROJECT}.kicad_sch"
    board = route.pcbnew.LoadBoard(str(board_path))
    if board is None:
        raise SystemExit(f"Cannot load {board_path}")
    route.verify_board_pin_nets(board)
    route.verify_reference_component_pinouts(board)
    netlist = route.verify_schematic_netlist()

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
        "-o",
        str(drc),
        str(board_path),
    )
    route.require_erc_clean(erc)
    drc_text = drc.read_text(encoding="utf-8")
    require(r"\*\* Found 0 DRC violations \*\*", drc_text, "DRC")
    require(r"\*\* Found 0 unconnected pads \*\*", drc_text, "connection")
    require(r"\*\* Found 0 Footprint errors \*\*", drc_text, "parity")
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
        ]
    )
    print(
        f"PASS board={board_path} netlist={netlist} erc={erc} drc={drc} "
        f"manifest={manifest}"
    )


if __name__ == "__main__":
    main()
