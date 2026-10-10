#!/usr/bin/env python3
"""Create an immutable-input KiCad fabrication variant without DNP paste.

Run with KiCad's bundled Python so ``pcbnew`` is available.  This changes only
the F.Paste/B.Paste membership of pads belonging to footprints marked DNP.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pcbnew


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_refs(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--expect-dnp",
        default="",
        help="Optional comma-separated exact DNP reference set",
    )
    args = parser.parse_args()

    source = args.input.resolve()
    destination = args.output.resolve()
    if source == destination:
        raise SystemExit("Refusing to overwrite the canonical PCB")
    if not source.is_file():
        raise SystemExit(f"PCB does not exist: {source}")

    board = pcbnew.LoadBoard(str(source))
    if board is None:
        raise SystemExit(f"Cannot load PCB: {source}")
    if not board.IsLayerEnabled(pcbnew.F_Paste):
        raise SystemExit("F.Paste is not enabled in the canonical PCB layer table")

    dnp_refs: set[str] = set()
    removed: list[dict[str, str]] = []
    for footprint in board.GetFootprints():
        if not footprint.IsDNP():
            continue
        reference = footprint.GetReference()
        dnp_refs.add(reference)
        for pad in footprint.Pads():
            layers = pad.GetLayerSet()
            paste_layers = []
            for layer, name in (
                (pcbnew.F_Paste, "F.Paste"),
                (pcbnew.B_Paste, "B.Paste"),
            ):
                if layers.Contains(layer):
                    paste_layers.append(name)
                    layers.RemoveLayer(layer)
            if paste_layers:
                pad.SetLayerSet(layers)
                removed.append(
                    {
                        "reference": reference,
                        "pad": pad.GetNumber(),
                        "layers": ",".join(paste_layers),
                    }
                )

    expected = parse_refs(args.expect_dnp)
    if expected and dnp_refs != expected:
        raise SystemExit(
            f"DNP set drift: expected={sorted(expected)}, actual={sorted(dnp_refs)}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(destination), board)
    reloaded = pcbnew.LoadBoard(str(destination))
    if reloaded is None:
        raise SystemExit("Cannot reload fabrication variant")
    residual = []
    for footprint in reloaded.GetFootprints():
        if not footprint.IsDNP():
            continue
        for pad in footprint.Pads():
            layers = pad.GetLayerSet()
            if layers.Contains(pcbnew.F_Paste) or layers.Contains(pcbnew.B_Paste):
                residual.append((footprint.GetReference(), pad.GetNumber()))
    if residual:
        raise SystemExit(f"DNP paste apertures remain after save: {residual}")

    report = {
        "schema": 1,
        "status": "PASS",
        "source": str(source),
        "source_sha256": sha256(source),
        "output": str(destination),
        "output_sha256": sha256(destination),
        "dnp_refs": sorted(dnp_refs),
        "removed_paste_apertures": sorted(
            removed, key=lambda item: (item["reference"], item["pad"])
        ),
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
