#!/usr/bin/env python3
"""Independent fail-closed checks for the B3 R3 staging builder.

This verifier is read-only with respect to the repository.  Its lock/hash
negative samples live only in an OS temporary directory; it does not load,
save or operate any KiCad board and never accesses attached hardware.
"""

from __future__ import annotations

import contextlib
import io
import tempfile
from pathlib import Path

import build_mf1750_wroom_b3_board_r3 as builder


def main() -> int:
    checks: dict[str, bool] = {}
    checks["canonical_schematic_path_frozen"] = (
        builder.CANONICAL_SCHEMATIC
        == builder.B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
    )
    checks["canonical_schematic_hash_frozen"] = (
        builder.sha256_file(builder.CANONICAL_SCHEMATIC)
        == builder.CANONICAL_SCHEMATIC_SHA256
    )
    checks["formal_board_is_not_staging_output"] = (
        builder.FORMAL_B3_BOARD.resolve() != builder.OUTPUT_BOARD.resolve()
    )
    checks["outline_frozen_80x125"] = (
        builder.DEFAULT_WIDTH_MM == 80.0
        and builder.DEFAULT_HEIGHT_MM == 125.0
    )
    failure = builder.failure_report(80.0, 125.0, "negative canary")
    checks["failure_report_is_not_pass"] = (
        failure["result"] == "FAIL"
        and failure["overall_status"] == "HOLD"
        and failure["passed"] is False
        and failure["sync_passed"] is False
        and failure["locally_verified"] is False
    )

    original_dirs = (builder.B2_DIR, builder.B3_DIR, builder.STAGING)
    with tempfile.TemporaryDirectory(prefix="mf1750-b3-gate-negative-") as name:
        root = Path(name)
        b2_dir = root / "b2"
        b3_dir = root / "b3"
        staging_dir = root / "staging"
        for directory in (b2_dir, b3_dir, staging_dir):
            directory.mkdir()
        lock = b3_dir / "~negative.kicad_sch.lck"
        lock.write_text("negative lock canary", encoding="utf-8")
        builder.B2_DIR = b2_dir
        builder.B3_DIR = b3_dir
        builder.STAGING = staging_dir
        try:
            checks["b3_root_lock_is_detected"] = builder.find_project_locks() == [
                lock.resolve()
            ]
        finally:
            builder.B2_DIR, builder.B3_DIR, builder.STAGING = original_dirs

        wrong_hash_file = root / "wrong.kicad_sch"
        wrong_hash_file.write_text("not the canonical schematic", encoding="utf-8")
        try:
            builder.require_exact_sha256(
                wrong_hash_file, "0" * 64, "negative hash canary"
            )
        except builder.BuildError:
            checks["wrong_hash_is_rejected"] = True
        else:
            checks["wrong_hash_is_rejected"] = False

    stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr):
            builder.parse_args(["--schematic", "redirected.kicad_sch"])
    except SystemExit as exc:
        checks["schematic_override_is_rejected"] = exc.code == 2
    else:
        checks["schematic_override_is_rejected"] = False

    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    print(f"SUMMARY {sum(checks.values())}/{len(checks)}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
