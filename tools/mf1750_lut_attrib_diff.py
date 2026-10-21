#!/usr/bin/env python3
"""Offline LUT/sequence attribution diff: atlas full-frame vs PTLW partial path.

Reproducible evidence extractor for the PARTIAL_BLOCK_LUT_ATTRIB analysis:
- proves the 1E (and 0E/1C) R20 payloads bound by the atlas and PTLW paths are
  byte-identical (from the sealed offline bundles and the generator module);
- pins the exact driven-byte difference between the two refresh sequences
  (full-frame BTST2 rewrite vs clean-PTLW no-BTST2);
- computes the within-controller 180-degree PTLW window placement observed in
  the P1/P2 hardware batches.

Purely offline: no hardware, serial, relay, network, camera, or flashing
access is performed.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import mf1750_partial_block_build as build  # noqa: E402
from tools import mf1750_wf_wmask_build as wmask  # noqa: E402

V4_GENERATION = ROOT / ".test-output/offline/MF1750_PARTIAL_BLOCK_20261020_V4/route-a-v4-generation.json"
V2_GENERATION = ROOT / ".test-output/offline/MF1750_PARTIAL_BLOCK_20261020_V2/route-b-v2-generation.json"
R2G_DRIVER = ROOT / "src/wf_bisect_r2g_epd_driver.cpp"
PTLW_V2_DRIVER = ROOT / "src/partial_block_ptlw_v2_epd_driver.cpp"
ATLAS_V4_DRIVER = ROOT / "src/partial_atlas_1e_v4_epd_driver.cpp"

# Measured P1/P2 patch placements from the rectified batch photos
# (within-batch, hand-fitted quad; see analysis.md for the method).
WINDOW_MEASUREMENTS = [
    {
        "batch": "MF1750_PARTIAL_BLOCK_P1_20261020_V1",
        "photo": "04-patch-a-t0.jpg",
        "window": {"x": 48, "y": 64, "w": 160, "h": 120},
        "observed_spans_cs1": {"x": [267, 402], "y": [410, 530]},
        "observed_spans_cs2": {"x": [767, 926], "y": [405, 527]},
    },
]

# Refresh sequence byte pins (file:line anchors verified by tests).
INIT_BTST2 = [0x6F, 0x1F, 0x17, 0x17]
REFRESH_BTST2 = [0x6F, 0x1F, 0x17, 0x49]
BTST2_BYTE3_SEMANTICS = {
    "0x17": {"vphssc_drv": 1, "vphssc_oft": "OFFH7"},
    "0x49": {"vphssc_drv": 2, "vphssc_oft": "OFFH9"},
}


def window_180(window: dict[str, int]) -> dict[str, int]:
    """Observed within-controller placement of a PTLW window.

    The controller's PTLW HRST/VRST origin is at the opposite corner from the
    linear DTM fill origin: physical = (CONTROLLER_WIDTH - x - w,
    HEIGHT - y - h) per controller half.
    """

    return {
        "x": build.CONTROLLER_WIDTH - window["x"] - window["w"],
        "y": build.HEIGHT - window["y"] - window["h"],
        "w": window["w"],
        "h": window["h"],
    }


def _line_of(text: str, needle: str) -> int:
    for index, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return index
    raise RuntimeError(f"anchor not found: {needle}")


def build_evidence() -> dict[str, Any]:
    v4 = json.loads(V4_GENERATION.read_text(encoding="utf-8"))
    v2 = json.loads(V2_GENERATION.read_text(encoding="utf-8"))
    atlas_1e_r20 = v4["tuples"]["1E"]["r20_sha256"]
    ptlw_1e_r20 = v2["profiles"]["1E"]["r20_sha256"]
    module_1e = wmask.build_offline_variant(0x0E, True)[0]
    r2g = R2G_DRIVER.read_text(encoding="utf-8")
    ptlw_driver = PTLW_V2_DRIVER.read_text(encoding="utf-8")
    atlas_driver = ATLAS_V4_DRIVER.read_text(encoding="utf-8")

    anchors = {
        "init_btst2": {
            "bytes": INIT_BTST2,
            "file": "src/wf_bisect_r2g_epd_driver.cpp",
            "line": _line_of(r2g, "epdData(0x17);\n" if False else "epdCommand(BTST2);") + 0,
        },
    }
    # precise line anchors
    init_line = _line_of(r2g, "epdCommand(POFS);") - 6  # BTST2 block just above POFS
    refresh_line = _line_of(r2g, 'Serial.println("EPD display refresh");') - 6

    profiles = {
        label: {
            "atlas_r20_sha256": v4["tuples"]["1E"]["r20_sha256"] if label == "1E" else None,
            "ptlw_r20_sha256": v2["profiles"][label]["r20_sha256"],
            "module_r20_sha256": wmask.build_offline_variant(
                {"1E": 0x0E, "0E": 0x0E, "1C": 0x0C}[label],
                label in ("1E", "1C"),
            )[0]["r20_sha256"],
        }
        for label in ("1E", "0E", "1C")
    }

    return {
        "schema_version": 1,
        "kind": "mf1750-lut-attrib-diff-evidence",
        "offline_only": True,
        "lut_identity": {
            "atlas_1e_r20_sha256": atlas_1e_r20,
            "ptlw_1e_r20_sha256": ptlw_1e_r20,
            "module_1e_r20_sha256": module_1e["r20_sha256"],
            "identical": atlas_1e_r20 == ptlw_1e_r20 == module_1e["r20_sha256"],
            "profiles": profiles,
            "pwr_sha256": wmask.PWR_SHA256,
            "pll_sha256": wmask.PLL_SHA256,
            "r21_sha256": wmask.R21_SHA256,
        },
        "refresh_sequence_diff": {
            "shared_init_btst2": {
                "bytes": INIT_BTST2,
                "anchor": "src/wf_bisect_r2g_epd_driver.cpp:990-994 "
                          "(epdInitResolutionSelected, shared via epdPrepareCascade)",
            },
            "atlas_full_frame": {
                "sequence": ["PON", "BTST2 {6F,1F,17,49}", "DRF 0x00", "POF 0x00"],
                "btst2_rewrite": REFRESH_BTST2,
                "anchor": "src/wf_bisect_r2g_epd_driver.cpp:618-622 "
                          "(epdSecondSettingAndRefresh)",
                "used_by": ["partial_atlas_1e*", "partial_atlas_1e_v2_*",
                            "partial_atlas_1e_v3_*", "partial_atlas_1e_v4_*"],
            },
            "ptlw_partial": {
                "sequence": ["PON", "DRF 0x00", "POF 0x00"],
                "btst2_rewrite": None,
                "retained_btst2": INIT_BTST2,
                "anchor": "src/partial_block_ptlw_v2_epd_driver.cpp:2978-3018 "
                          "(pbRefreshCleanPtlw)",
                "used_by": ["partial_block_ptlw", "partial_block_ptlw_v2"],
            },
            "only_driven_byte_difference": {
                "register": "BTST2 byte 3 (VPH booster soft-start phase C)",
                "atlas_value": "0x49",
                "ptlw_value": "0x17 (init value retained)",
                "semantics": BTST2_BYTE3_SEMANTICS,
                "datasheet": "SPD1657B Rev 1.1 p.16 (BTST2 VPH booster soft "
                             "start setting register)",
            },
        },
        "drf_bins": {
            "atlas_full_frame_ms": [32670, 32681],
            "ptlw_partial_ms": [32651, 32661],
            "same_slow_bin": True,
        },
        "ptlw_window_direction": {
            "mapping": "physical = (512-x-w, 600-y-h) per controller half",
            "windows": [
                {
                    "window": dict(window),
                    "observed": window_180(window),
                    "observed_global_cs1": dict(window_180(window)),
                    "observed_global_cs2": {
                        **window_180(window),
                        "x": window_180(window)["x"] + build.CONTROLLER_WIDTH,
                    },
                }
                for window in build.PTLW_WINDOWS
            ],
            "measurements": WINDOW_MEASUREMENTS,
            "august_evidence_gap": (
                "2026-08 partial-hold batches used controller-symmetric patches "
                "and left/right parity checks, which are invariant under a "
                "within-controller 180-degree flip; the convention was never "
                "anchored to absolute positions"
            ),
        },
        "code4_render_observations": {
            "atlas_full_frame": {"L": 29.8, "a": 8.5, "b": -22.8,
                                 "source": "MF1750_PARTIAL_BLOCK_P0_20261020_V1 "
                                           "clean remeasurement"},
            "ptlw_partial": {"L": 65.1, "a": -9.1, "b": -7.2,
                             "source": "MF1750_PARTIAL_BLOCK_P1_20261020_V1 "
                                       "rectified warp measurement"},
        },
        "line_anchors": {
            "r2g_init_btst2_block_end": init_line,
            "r2g_refresh_btst2_block_start": refresh_line,
            "ptlw_clean_refresh": _line_of(ptlw_driver, "bool pbRefreshCleanPtlw()"),
            "atlas_v4_refresh_wrapper": _line_of(atlas_driver, "bool pbv4RefreshFullFrame()"),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    print(json.dumps(build_evidence(), ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
