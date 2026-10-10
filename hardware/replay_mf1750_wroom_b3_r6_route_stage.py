#!/usr/bin/env python3
"""Replay an audited R5 route engine into R6-only staging artifacts.

The R5 route builders are immutable evidence for the reviewed R5 candidate.
This adapter hash-binds their source text, rewrites only stage labels/artifact
names and the deterministic UUID seed in memory, then invokes the resulting
engine against an explicit hash-bound R6 source.  It never edits an R5 file or
artifact and it independently rechecks the formal/R3/R4 protected boards.

The BQ engine compares footprint geometry with a baseline board.  For that
stage ``--r6-placement`` is therefore mandatory and becomes the comparison
baseline; the original R4 board is still independently hash-protected here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import types
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
R3_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r3_placed.kicad_pcb"
R4_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r4_functional_placed.kicad_pcb"

PROTECTED_SHA256 = {
    FORMAL_BOARD: "6da0e247e50ba4ce9ea984d6f0da72d98c1ac31544bf1aecbbb449bf3707e3a7",
    R3_BOARD: "c43446b3ba92a7ee6c2aa2af2ad89761a81902d5d8be58e315297d5161df22fb",
    R4_BOARD: "349ef014b520aedcb061ee8bbcadbb03bfaad3249b512937091280918d0f2fbf",
}

STAGES: dict[str, dict[str, Any]] = {
    "u4": {
        "engine": HARDWARE / "route_mf1750_wroom_b3_r5_u4.py",
        "engine_sha256": "8405cd8f8892566626f00f7b34170d0f2a606013af934677343bc40715424257",
        "seed_name": "ROUTING_UUID_SEED",
        "old_seed": 17505,
        "new_seed": 17510,
        "output": STAGING / "mf1750_wroom_b3_power_tf_r6_u4_routed.kicad_pcb",
        "audit": STAGING / "r6_u4_route_audit.json",
        "drc": STAGING / "r6_u4_drc.json",
        "preview_dir": STAGING / "r6_u4_preview",
        "top_preview": "mf1750_wroom_b3_power_tf_r6_u4_top.png",
        "bottom_preview": "mf1750_wroom_b3_power_tf_r6_u4_bottom.png",
        "safe_replacements": {
            "MF1750 WROOM B3 R5 TPS63070 critical-loop route candidate": "MF1750 WROOM B3 R6 TPS63070 critical-loop route candidate",
            "B3-WROOM-POWER-TF-R5-U4-ROUTED": "B3-WROOM-POWER-TF-R6-U4-ROUTED",
            "R5_U4_PARTIALLY_ROUTED_CANDIDATE": "R6_U4_PARTIALLY_ROUTED_CANDIDATE",
            "HOLD_R5_U4_ROUTE_FAILED": "HOLD_R6_U4_ROUTE_FAILED",
        },
    },
    "bq": {
        "engine": HARDWARE / "route_mf1750_wroom_b3_bq_power_r5.py",
        "engine_sha256": "3a338ed1327aea23ecb7f214aab066fa136328361dcfcbe29ffb464c490514c6",
        "seed_name": "ROUTE_UUID_SEED",
        "old_seed": 17506,
        "new_seed": 17511,
        "output": STAGING / "mf1750_wroom_b3_power_tf_r6_bq_powerpath_routed.kicad_pcb",
        "audit": STAGING / "r6_bq_powerpath_route_audit.json",
        "drc": STAGING / "r6_bq_powerpath_drc.json",
        "preview_dir": STAGING / "r6_bq_powerpath_preview",
        "top_preview": "mf1750_wroom_b3_power_tf_r6_bq_top.png",
        "bottom_preview": "mf1750_wroom_b3_power_tf_r6_bq_bottom.png",
        "safe_replacements": {
            "B3-WROOM-POWER-TF-R5-BQ-POWERPATH": "B3-WROOM-POWER-TF-R6-BQ-POWERPATH",
            "R5_BQ_POWERPATH_ROUTED_CANDIDATE_PARTIAL_BOARD": "R6_BQ_POWERPATH_ROUTED_CANDIDATE_PARTIAL_BOARD",
        },
    },
}


class ReplayError(RuntimeError):
    """Raised when the replay evidence contract is not satisfied."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_hash(value: str, label: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ReplayError(f"{label} must contain exactly 64 hexadecimal characters")
    return value.casefold()


def protected_snapshot() -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path, expected in PROTECTED_SHA256.items():
        if not path.is_file():
            raise ReplayError(f"protected source missing: {path}")
        actual = sha256_file(path)
        if actual != expected:
            raise ReplayError(f"protected source hash mismatch: {path}: {actual} != {expected}")
        snapshot[str(path)] = actual
    return snapshot


def load_engine(stage: str) -> dict[str, Any]:
    spec = STAGES[stage]
    engine_path: Path = spec["engine"]
    if not engine_path.is_file():
        raise ReplayError(f"route engine missing: {engine_path}")
    actual = sha256_file(engine_path)
    if actual != spec["engine_sha256"]:
        raise ReplayError(
            f"route engine hash mismatch: {actual} != {spec['engine_sha256']}"
        )
    source_text = engine_path.read_text(encoding="utf-8")
    # Only exact metadata literals are transformed.  A broad "R5" replace is
    # forbidden because valid references R51-R59 occur in the route engines.
    transformed = source_text
    for old, new in spec["safe_replacements"].items():
        if transformed.count(old) != 1:
            raise ReplayError(f"route engine metadata contract drift: {old!r}")
        transformed = transformed.replace(old, new)
    module_name = f"_mf1750_wroom_b3_r6_{stage}_engine"
    module = types.ModuleType(module_name)
    module.__file__ = str(Path(__file__).resolve())
    # dataclasses resolves postponed annotations through sys.modules while the
    # class decorator runs, so the in-memory engine must be registered first.
    sys.modules[module_name] = module
    exec(
        compile(transformed, str(Path(__file__).resolve()), "exec"),
        module.__dict__,
    )
    namespace = module.__dict__
    seed_name = spec["seed_name"]
    if namespace.get(seed_name) != spec["old_seed"]:
        raise ReplayError(f"route engine seed contract drift: {seed_name}")
    namespace[seed_name] = spec["new_seed"]
    namespace["OUTPUT_BOARD"] = spec["output"]
    namespace["AUDIT_JSON"] = spec["audit"]
    namespace["DRC_JSON"] = spec["drc"]
    namespace["PREVIEW_DIR"] = spec["preview_dir"]
    namespace["TOP_PREVIEW"] = spec["preview_dir"] / spec["top_preview"]
    namespace["BOTTOM_PREVIEW"] = spec["preview_dir"] / spec["bottom_preview"]
    return namespace


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=tuple(STAGES), required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument(
        "--r6-placement",
        type=Path,
        help="required for BQ; hash-bound R6 footprint-geometry baseline",
    )
    parser.add_argument("--r6-placement-sha256")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    before = protected_snapshot()
    source = args.source.resolve()
    source_sha = validate_hash(args.source_sha256, "--source-sha256")
    if not source.is_file() or sha256_file(source) != source_sha:
        raise ReplayError(f"R6 source is missing or hash-mismatched: {source}")

    engine = load_engine(args.stage)
    if args.stage == "bq":
        if args.r6_placement is None or args.r6_placement_sha256 is None:
            raise ReplayError("BQ replay requires --r6-placement and its SHA-256")
        placement = args.r6_placement.resolve()
        placement_sha = validate_hash(
            args.r6_placement_sha256, "--r6-placement-sha256"
        )
        if not placement.is_file() or sha256_file(placement) != placement_sha:
            raise ReplayError(
                f"R6 placement baseline is missing or hash-mismatched: {placement}"
            )
        engine["R4_BOARD"] = placement
        engine["R4_SHA256"] = placement_sha

    result = int(
        engine["main"](
            ["--source", str(source), "--source-sha256", source_sha]
        )
    )
    after = protected_snapshot()
    if after != before:
        raise ReplayError("a protected formal/R3/R4 board changed during R6 replay")

    audit_path: Path = STAGES[args.stage]["audit"]
    if result == 0:
        if not audit_path.is_file():
            raise ReplayError(f"R6 engine did not create its audit: {audit_path}")
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit["r6_replay_adapter"] = {
            "adapter": str(Path(__file__).resolve()),
            "engine": str(STAGES[args.stage]["engine"]),
            "engine_sha256": STAGES[args.stage]["engine_sha256"],
            "source_sha256": source_sha,
            "protected_originals": after,
        }
        audit_path.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
