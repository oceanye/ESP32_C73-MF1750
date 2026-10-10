#!/usr/bin/env python3
"""Offline binding adapter for the lineage-repair candidate.

This module only verifies the isolated manifest and exports its BIN/ELF
identity. It deliberately has no serial, network, relay, camera, or runner
mutation entry point.
"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT
    / ".test-output/offline/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_LINEAGE_REPAIR_20260912_LH4/lineage-repair-offline-build.json"
)
BIN = ROOT / ".pio/br_lhr4/lhr4/firmware.bin"
ELF = ROOT / ".pio/br_lhr4/lhr4/firmware.elf"


def validate() -> dict:
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    body = dict(value)
    integrity = body.pop("integrity")
    canonical = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    if integrity.get("sha256") != hashlib.sha256(canonical).hexdigest():
        raise RuntimeError("repair manifest integrity differs")
    for label, path in (("firmware.bin", BIN), ("firmware.elf", ELF)):
        expected = value["successor_artifacts"][label]
        if (
            path.stat().st_size != expected["bytes"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]
        ):
            raise RuntimeError(f"{label} candidate hash differs")
    if value.get("semantic_diff", {}).get("semantic_scope") != "identityJson only":
        raise RuntimeError("repair scope differs")
    return {
        "result": "PASS",
        "offline_only": True,
        "hardware_accessed": False,
        "manifest": str(MANIFEST.relative_to(ROOT)),
        "bin_sha256": value["successor_artifacts"]["firmware.bin"]["sha256"],
        "elf_sha256": value["successor_artifacts"]["firmware.elf"]["sha256"],
        "live_use": "requires a new independently sealed pack/runner; original LH1 source-firmware binding is incompatible; preserve original NVS/claims",
    }


if __name__ == "__main__":
    print(json.dumps(validate(), ensure_ascii=False, sort_keys=True))
