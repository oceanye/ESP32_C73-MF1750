#!/usr/bin/env python3
"""Replay the EPD boundary route for the R6 SI-remediated placement.

This staging-only wrapper deliberately reuses the audited R5 route engine but
changes the parts whose geometry or layer assignment is invalid after the R6
placement review.  It moves every former In1 signal route to the permitted
low-speed In2 layer so In1 remains the continuous GND reference plane, moves
the U6 OE escape clear of the relocated bypass capacitor, and terminates the
inherited CS2 tail at its real open end.  A hash-bound source is mandatory.

The R5 script and all R5 evidence remain immutable; this file produces only
R6-named staging artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import types
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "hardware" / "route_mf1750_wroom_b3_epd_boundary_r5.py"
ENGINE_SHA256 = "28f43841aed156a9f1f7697f432a3e95b5205fd85529fb291851eddd9a0cee41"
STAGING = ROOT / "hardware" / "mf1750_wroom_b3_power_tf" / "staging"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_r6_engine() -> types.ModuleType:
    if not ENGINE.is_file() or _sha256_file(ENGINE) != ENGINE_SHA256:
        raise RuntimeError(f"R5 EPD route engine missing or hash-mismatched: {ENGINE}")
    source_text = ENGINE.read_text(encoding="utf-8")
    # Never broadly replace "R5": the engine contains valid references
    # R54-R59.  Only the two report-state literals are metadata.
    transformed = source_text
    replacements = {
        "R5_EPD_BOUNDARY_ROUTED_CANDIDATE": "R6_EPD_BOUNDARY_ROUTED_CANDIDATE",
        "R5_EPD_BOUNDARY_ROUTE_FAILED": "R6_EPD_BOUNDARY_ROUTE_FAILED",
    }
    for old, new in replacements.items():
        if transformed.count(old) != 1:
            raise RuntimeError(f"R5 EPD metadata contract drift: {old}")
        transformed = transformed.replace(old, new)
    module_name = "_mf1750_wroom_b3_r6_epd_engine"
    module = types.ModuleType(module_name)
    module.__file__ = str(Path(__file__).resolve())
    sys.modules[module_name] = module
    exec(compile(transformed, str(Path(__file__).resolve()), "exec"), module.__dict__)
    return module


base = _load_r6_engine()


def _rewrite_routes(
    routes: tuple[tuple[str, str, float, tuple[tuple[float, float], ...]], ...]
) -> tuple[tuple[str, str, float, tuple[tuple[float, float], ...]], ...]:
    rewritten = []
    replaced_c45 = 0
    replaced_cs2 = 0
    replaced_oe_escape = 0
    replaced_oe_inner = 0
    replaced_rst_escape = 0
    bridged_long_returns = 0
    migrated_in1 = 0
    for net, layer, width, points in routes:
        if (
            net == "/EPD_3V3"
            and layer == "F.Cu"
            and points
            == ((35.700, 60.400), (26.725, 60.400), (26.725, 62.500))
        ):
            # C45 is now immediately to the right of U6.  The local bypass
            # branch therefore leaves U6 pad 20 instead of crossing 10 mm to
            # the former capacitor location.
            rewritten.append(
                (
                    net,
                    layer,
                    width,
                    (
                        (36.8625, 62.575),
                        (37.2000, 62.000),
                        (38.9000, 62.000),
                        (39.2250, 62.500),
                    ),
                )
            )
            replaced_c45 += 1
            continue
        if (
            net == "/EPD_BUF_OE_N"
            and layer == "F.Cu"
            and points == ((36.8625, 63.225), (38.200, 63.225))
        ):
            rewritten.append(
                (net, layer, width, ((36.8625, 63.225), (38.1000, 63.225)))
            )
            replaced_oe_escape += 1
            continue
        if (
            net == "/EPD_BUF_OE_N"
            and layer == "In1.Cu"
            and points
            == ((38.200, 63.225), (35.200, 61.500), (24.800, 61.500))
        ):
            rewritten.append(
                (
                    net,
                    "In2.Cu",
                    width,
                    ((38.1000, 63.225), (35.200, 61.500), (24.800, 61.500)),
                )
            )
            replaced_oe_inner += 1
            migrated_in1 += 1
            continue
        if (
            net == "/RST_N"
            and layer == "In2.Cu"
            and points
            == ((39.500, 63.875), (44.000, 61.500), (62.000, 61.500))
        ):
            # Preserve the proven ordered fanout.  The relocated C45 ground
            # drop is moved above this diagonal instead of disturbing the
            # seven-channel escape ordering.
            rewritten.append((net, layer, width, points))
            replaced_rst_escape += 1
            continue
        if net == "/CS2" and layer == "F.Cu" and points[-1] == (48.9381, 57.588):
            # The R5 join touched the connected end of the inherited tail and
            # left its far end dangling.  Join at the real B2 endpoint instead;
            # the inherited segment then carries CS2 into the proven network.
            rewritten.append((net, layer, width, (*points[:-1], (45.0120, 57.5880))))
            replaced_cs2 += 1
            continue
        if net == "/RST_N" and layer == "In1.Cu" and points == (
            (62.000, 61.500),
            (62.000, 57.000),
            (12.000, 57.000),
        ):
            rewritten.extend(
                (
                    (net, "In2.Cu", width, ((62.000, 61.500), (62.000, 57.000), (61.750, 57.000))),
                    (net, "B.Cu", width, ((61.750, 57.000), (60.250, 57.000))),
                    (net, "In2.Cu", width, ((60.250, 57.000), (12.000, 57.000))),
                )
            )
            migrated_in1 += 1
            bridged_long_returns += 1
            continue
        if net == "/DC" and layer == "In1.Cu" and points == (
            (41.000, 64.525),
            (44.000, 62.500),
            (63.000, 62.500),
            (63.000, 56.000),
            (18.000, 56.000),
        ):
            rewritten.extend(
                (
                    (
                        net,
                        "In2.Cu",
                        width,
                        (
                            (41.000, 64.525),
                            (44.000, 62.500),
                            (63.000, 62.500),
                            (63.000, 56.000),
                            (61.750, 55.250),
                        ),
                    ),
                    (net, "B.Cu", width, ((61.750, 55.250), (60.250, 55.250))),
                    (net, "In2.Cu", width, ((60.250, 55.250), (58.500, 56.000), (18.000, 56.000))),
                )
            )
            migrated_in1 += 1
            bridged_long_returns += 1
            continue
        if net == "/CSB" and layer == "In1.Cu" and points == (
            (42.000, 65.175),
            (45.000, 63.500),
            (64.000, 63.500),
            (64.000, 55.000),
            (25.000, 55.000),
        ):
            rewritten.extend(
                (
                    (
                        net,
                        "In2.Cu",
                        width,
                        (
                            (42.000, 65.175),
                            (45.000, 63.500),
                            (64.000, 63.500),
                            (64.000, 55.000),
                            (61.750, 54.250),
                        ),
                    ),
                    (net, "B.Cu", width, ((61.750, 54.250), (60.250, 54.250))),
                    (net, "In2.Cu", width, ((60.250, 54.250), (58.500, 55.000), (25.000, 55.000))),
                )
            )
            migrated_in1 += 1
            bridged_long_returns += 1
            continue
        if net == "/SCL" and layer == "In1.Cu" and points == (
            (38.200, 66.475),
            (43.500, 66.475),
            (46.000, 64.500),
            (65.000, 64.500),
            (65.000, 53.500),
            (46.000, 53.500),
        ):
            rewritten.extend(
                (
                    (
                        net,
                        "In2.Cu",
                        width,
                        (
                            (38.200, 66.475),
                            (43.500, 66.475),
                            (46.000, 64.500),
                            (65.000, 64.500),
                            (65.000, 53.500),
                            (61.750, 53.250),
                        ),
                    ),
                    (net, "B.Cu", width, ((61.750, 53.250), (60.250, 53.250))),
                    (net, "In2.Cu", width, ((60.250, 53.250), (58.500, 53.500), (46.000, 53.500))),
                )
            )
            migrated_in1 += 1
            bridged_long_returns += 1
            continue
        if net == "/SI0" and layer == "In1.Cu" and points == (
            (39.000, 67.125),
            (44.000, 68.200),
            (47.000, 65.500),
            (66.000, 65.500),
            (66.000, 52.500),
            (49.000, 52.500),
        ):
            rewritten.extend(
                (
                    (
                        net,
                        "In2.Cu",
                        width,
                        (
                            (39.000, 67.125),
                            (44.000, 68.200),
                            (47.000, 65.500),
                            (66.000, 65.500),
                            (66.000, 52.500),
                            (61.750, 51.750),
                        ),
                    ),
                    (net, "B.Cu", width, ((61.750, 51.750), (60.250, 51.750))),
                    (net, "In2.Cu", width, ((60.250, 51.750), (58.500, 52.500), (49.000, 52.500))),
                )
            )
            migrated_in1 += 1
            bridged_long_returns += 1
            continue
        if layer == "In1.Cu":
            layer = "In2.Cu"
            migrated_in1 += 1
        rewritten.append((net, layer, width, points))
    if (
        replaced_c45 != 1
        or replaced_cs2 != 1
        or replaced_oe_escape != 1
        or replaced_oe_inner != 1
        or replaced_rst_escape != 1
        or bridged_long_returns != 5
        or migrated_in1 != 9
    ):
        raise RuntimeError(
            "R5 route contract drift: "
            f"c45={replaced_c45}, cs2={replaced_cs2}, "
            f"oe_escape={replaced_oe_escape}, oe_inner={replaced_oe_inner}, "
            f"rst_escape={replaced_rst_escape}, bridges={bridged_long_returns}, "
            f"in1={migrated_in1}"
        )
    return tuple(rewritten)


def _replace_ground_contract() -> None:
    old_stub = ((28.275, 62.500), (29.600, 62.500))
    old_via = ("GND", 29.600, 62.500)
    stubs = []
    replaced_stub = 0
    for stub in base.GROUND_STUBS:
        if stub == old_stub:
            stubs.append(((40.775, 62.500), (42.000, 61.600)))
            replaced_stub += 1
        else:
            stubs.append(stub)
    vias = []
    replaced_via = 0
    for via in base.VIAS:
        if via == old_via:
            vias.append(("GND", 42.000, 61.600))
            replaced_via += 1
        else:
            vias.append(via)
    if replaced_stub != 1 or replaced_via != 1:
        raise RuntimeError(
            f"R5 ground contract drift: stub={replaced_stub}, via={replaced_via}"
        )
    base.GROUND_STUBS = tuple(stubs)
    base.VIAS = tuple(vias)


def _replace_signal_vias() -> None:
    old_via = ("/EPD_BUF_OE_N", 38.200, 63.225)
    vias = []
    replaced_oe = 0
    removed_redundant_rst = 0
    for via in base.VIAS:
        if via == old_via:
            vias.append(("/EPD_BUF_OE_N", 38.100, 63.225))
            replaced_oe += 1
        elif via == ("/RST_N", 62.000, 61.500):
            removed_redundant_rst += 1
        else:
            vias.append(via)
    bridge_vias = (
        ("/SI0", 60.250, 51.750),
        ("/SI0", 61.750, 51.750),
        ("/SCL", 60.250, 53.250),
        ("/SCL", 61.750, 53.250),
        ("/CSB", 60.250, 54.250),
        ("/CSB", 61.750, 54.250),
        ("/DC", 60.250, 55.250),
        ("/DC", 61.750, 55.250),
        ("/RST_N", 60.250, 57.000),
        ("/RST_N", 61.750, 57.000),
    )
    vias.extend(bridge_vias)
    if replaced_oe != 1 or removed_redundant_rst != 1:
        raise RuntimeError(
            "R5 signal-via contract drift: "
            f"oe={replaced_oe}, rst={removed_redundant_rst}"
        )
    base.VIAS = tuple(vias)


def configure_r6() -> None:
    base.__file__ = __file__
    base.OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r6_epd_boundary_routed.kicad_pcb"
    base.AUDIT_JSON = STAGING / "r6_epd_boundary_route_report.json"
    base.SOURCE_DRC_JSON = STAGING / "r6_epd_boundary_source_drc.json"
    base.CANDIDATE_DRC_JSON = STAGING / "r6_epd_boundary_drc.json"
    base.PREVIEW_DIR = STAGING / "r6_epd_boundary_preview"
    base.TOP_PREVIEW = base.PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r6_epd_boundary_top.png"
    base.BOTTOM_PREVIEW = base.PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r6_epd_boundary_bottom.png"
    base.FRONT_COPPER_SVG = base.PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r6_epd_boundary_front.svg"
    base.BACK_COPPER_SVG = base.PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r6_epd_boundary_back.svg"
    base.ROUTING_UUID_SEED = 17509

    pad_contract = dict(base.PAD_CONTRACT)
    pad_contract[("C45", "1")] = ("/EPD_3V3", 39.2250, 62.5000)
    pad_contract[("C45", "2")] = ("GND", 40.7750, 62.5000)
    base.PAD_CONTRACT = pad_contract
    base.ROUTES = _rewrite_routes(base.ROUTES)
    _replace_ground_contract()
    _replace_signal_vias()


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    configure_r6()
    return base.main(
        [
            "--source",
            str(args.source.resolve()),
            "--source-sha256",
            args.source_sha256,
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
