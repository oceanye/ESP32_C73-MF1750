#!/usr/bin/env python3
"""Build the final staging R8c EPD + internal + DCDC_PG + edge candidate.

The SHA-frozen DCDC_PG board is the sole PCB source.  The mutation remains
the proven edge-access whitelist.  Independent subset-chain audits preserve
the 102 EPD/MCU, 5 internal-control, and 7 DCDC_PG additive copper objects by
UUID and exact geometry.  No formal project artifact is written.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import build_mf1750_wroom_b3_r8b_epd_internal_edge_access as r8b


r8 = r8b.r8
edge = r8b.edge
pcbnew = r8b.pcbnew

ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8b_dcdc_pg_routed.kicad_pcb"
SOURCE_BOARD_SHA256 = (
    "a07aede19ece6e805b9510baa28435c52b40570cc45d7082645c9bf6d93e3269"
)
R8A_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8a_internal_control_routed.kicad_pcb"
R8A_BOARD_SHA256 = (
    "6f933e75a69552b32a2cea6fdfa802a6a24605a373baf8c77d43ee43bbda4ae8"
)
EPD_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r7_epd_mcu_routed.kicad_pcb"
EPD_BOARD_SHA256 = (
    "adf3a61c2231049f4a50b6ba97d95d5bd7b7fe9ff54be3f27469eb3f78cdc009"
)
HYGIENE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r7_drc_hygiene.kicad_pcb"
HYGIENE_BOARD_SHA256 = (
    "88dfc906bd8d15adccecc54ccdbb9a6d2e5f1ec3149ede199475923ba22c1cf8"
)

R8B_EDGE_ENGINE = HARDWARE / "build_mf1750_wroom_b3_r8b_epd_internal_edge_access.py"
R8B_EDGE_ENGINE_SHA256 = (
    "042b27a206fa7317d1439515cb207e2a066a9f2e97d06392153336fe831b07c0"
)
DCDC_ROUTE_BUILDER = HARDWARE / "route_mf1750_wroom_b3_dcdc_pg_r8b.py"
DCDC_ROUTE_BUILDER_SHA256 = (
    "6f595cf24445394e6beb9b1f5047ecaf0faab542facda19bf3a6b9e67d33b15b"
)
DCDC_ROUTE_REPORT = STAGING / "r8b_dcdc_pg_route_report.json"
DCDC_ROUTE_REPORT_SHA256 = (
    "3b507766762bddf1bb2e143484c69ca792db7e2229ca976b6b76b498b44b7b45"
)

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8c_epd_internal_dcdc_pg_edge_access.kicad_pcb"
OUTPUT_REPORT = STAGING / "r8c_epd_internal_dcdc_pg_edge_access_report.json"
OUTPUT_DRC = STAGING / "r8c_epd_internal_dcdc_pg_edge_access_drc.json"
PREVIEW_DIR = STAGING / "r8c_epd_internal_dcdc_pg_edge_access_preview"
OUTPUT_TOP = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8c_epd_internal_dcdc_pg_edge_access_top.png"
OUTPUT_BOTTOM = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8c_epd_internal_dcdc_pg_edge_access_bottom.png"

EXPECTED_SOURCE_COPPER = 1229
EXPECTED_CANDIDATE_COPPER = 1229
EXPECTED_SOURCE_UNCONNECTED = 126
EXPECTED_CANDIDATE_UNCONNECTED = 124


class FinalRebaseError(r8b.UnifiedError):
    """Fail-closed R8c route-chain preservation error."""


def configure() -> None:
    r8b.configure()
    protected = dict(r8.PROTECTED_HASHES)
    protected[SOURCE_BOARD] = SOURCE_BOARD_SHA256
    protected[R8A_BOARD] = R8A_BOARD_SHA256
    protected[EPD_BOARD] = EPD_BOARD_SHA256
    protected[HYGIENE_BOARD] = HYGIENE_BOARD_SHA256
    protected[R8B_EDGE_ENGINE] = R8B_EDGE_ENGINE_SHA256
    protected[DCDC_ROUTE_BUILDER] = DCDC_ROUTE_BUILDER_SHA256
    protected[DCDC_ROUTE_REPORT] = DCDC_ROUTE_REPORT_SHA256

    r8.SOURCE_BOARD = SOURCE_BOARD
    r8.SOURCE_BOARD_SHA256 = SOURCE_BOARD_SHA256
    r8.R7_HYGIENE_BOARD = HYGIENE_BOARD
    r8.R7_HYGIENE_SHA256 = HYGIENE_BOARD_SHA256
    r8.OUTPUT_BOARD = OUTPUT_BOARD
    r8.OUTPUT_REPORT = OUTPUT_REPORT
    r8.OUTPUT_DRC = OUTPUT_DRC
    r8.PREVIEW_DIR = PREVIEW_DIR
    r8.OUTPUT_TOP = OUTPUT_TOP
    r8.OUTPUT_BOTTOM = OUTPUT_BOTTOM
    r8.EXPECTED_SOURCE_COPPER = EXPECTED_SOURCE_COPPER
    r8.EXPECTED_CANDIDATE_COPPER = EXPECTED_CANDIDATE_COPPER
    r8.EXPECTED_SOURCE_UNCONNECTED = EXPECTED_SOURCE_UNCONNECTED
    r8.EXPECTED_CANDIDATE_UNCONNECTED = EXPECTED_CANDIDATE_UNCONNECTED
    r8.PROTECTED_HASHES = protected
    r8.__file__ = str(Path(__file__).resolve())

    r8.epd_route_preservation = final_route_chain_preservation
    r8.validate_r8_drc = validate_r8c_drc
    r8.json_bytes = r8c_json_bytes


def drift(
    ids: set[str], before: Mapping[str, Any], after: Mapping[str, Any]
) -> list[str]:
    return sorted(
        uuid for uuid in ids if uuid not in after or before[uuid] != after[uuid]
    )


def final_route_chain_preservation(candidate_path: Path) -> dict[str, Any]:
    _, hygiene, _ = r8b.state(HYGIENE_BOARD)
    _, epd, _ = r8b.state(EPD_BOARD)
    _, r8a, _ = r8b.state(R8A_BOARD)
    _, source, source_objects = r8b.state(SOURCE_BOARD)
    _, candidate, _ = r8b.state(candidate_path)

    hygiene_ids = set(hygiene)
    epd_ids_all = set(epd)
    r8a_ids = set(r8a)
    source_ids = set(source)
    candidate_ids = set(candidate)
    epd_ids = epd_ids_all - hygiene_ids
    internal_ids = r8a_ids - epd_ids_all
    dcdc_ids = source_ids - r8a_ids
    source_non_vbus = source_ids - set(edge.SOURCE_USB_VBUS_TRACK_UUIDS)
    replacement_ids = candidate_ids - source_non_vbus

    epd_objects = {uuid: source_objects[uuid] for uuid in epd_ids}
    internal_objects = {uuid: source_objects[uuid] for uuid in internal_ids}
    dcdc_objects = {uuid: source_objects[uuid] for uuid in dcdc_ids}
    hygiene_epd_drift = drift(hygiene_ids, hygiene, epd)
    epd_r8a_drift = drift(epd_ids_all, epd, r8a)
    r8a_source_drift = drift(r8a_ids, r8a, source)
    epd_candidate_drift = drift(epd_ids, source, candidate)
    internal_candidate_drift = drift(internal_ids, source, candidate)
    dcdc_candidate_drift = drift(dcdc_ids, source, candidate)
    retained_drift = drift(source_non_vbus, source, candidate)

    checks = {
        "hygiene_count_1115": len(hygiene_ids) == 1115,
        "epd_source_count_1217": len(epd_ids_all) == 1217,
        "r8a_source_count_1222": len(r8a_ids) == 1222,
        "dcdc_source_count_1229": len(source_ids) == EXPECTED_SOURCE_COPPER,
        "candidate_count_1229": len(candidate_ids) == EXPECTED_CANDIDATE_COPPER,
        "hygiene_exact_subset_of_epd": hygiene_ids <= epd_ids_all
        and not hygiene_epd_drift,
        "epd_exact_subset_of_r8a": epd_ids_all <= r8a_ids and not epd_r8a_drift,
        "r8a_exact_subset_of_dcdc_source": r8a_ids <= source_ids
        and not r8a_source_drift,
        "epd_set_exactly_102": len(epd_ids) == 102,
        "internal_set_exactly_5": len(internal_ids) == 5,
        "dcdc_pg_set_exactly_7": len(dcdc_ids) == 7,
        "epd_geometry_74_tracks_28_vias": r8b.kind_counts(epd_objects)
        == {"track": 74, "via": 28},
        "internal_geometry_4_tracks_1_via": r8b.kind_counts(internal_objects)
        == {"track": 4, "via": 1},
        "dcdc_geometry_5_tracks_2_vias": r8b.kind_counts(dcdc_objects)
        == {"track": 5, "via": 2},
        "internal_net_exact": {
            item.GetNetname() for item in internal_objects.values()
        }
        == {"/USB_INPUT_VALID_N"},
        "dcdc_pg_net_exact": {
            item.GetNetname() for item in dcdc_objects.values()
        }
        == {"/DCDC_PG"},
        "all_102_epd_preserved": not epd_candidate_drift,
        "all_5_internal_preserved": not internal_candidate_drift,
        "all_7_dcdc_pg_preserved": not dcdc_candidate_drift,
        "all_source_non_vbus_preserved": not retained_drift,
        "only_exact_eight_source_vbus_removed": not (
            set(edge.SOURCE_USB_VBUS_TRACK_UUIDS) & candidate_ids
        ),
        "exactly_eight_replacement_vbus_added": len(replacement_ids) == 8,
    }
    if not all(checks.values()):
        raise FinalRebaseError(
            "R8c route-chain preservation failed: "
            + json.dumps(checks, ensure_ascii=False, sort_keys=True)
        )

    def group(ids: set[str], objects: Mapping[str, Any], missing: list[str]) -> dict[str, Any]:
        return {
            "count": len(ids),
            "kind_counts": r8b.kind_counts(objects),
            "by_net": r8b.net_counts(objects),
            "uuid_signature_sha256": r8b.digest(
                {uuid: source[uuid] for uuid in ids}
            ),
            "uuids": sorted(ids),
            "missing_or_changed": missing,
        }

    return {
        "passed": True,
        "checks": checks,
        "counts": {
            "hygiene": len(hygiene_ids),
            "epd_source": len(epd_ids_all),
            "r8a_source": len(r8a_ids),
            "dcdc_source": len(source_ids),
            "candidate": len(candidate_ids),
        },
        "epd_102": group(epd_ids, epd_objects, epd_candidate_drift),
        "internal_5": group(
            internal_ids, internal_objects, internal_candidate_drift
        ),
        "dcdc_pg_7": group(dcdc_ids, dcdc_objects, dcdc_candidate_drift),
        "other_retained_copper_drift": retained_drift,
        "replacement_vbus_uuids": sorted(replacement_ids),
    }


def validate_r8c_drc(
    source: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    result = edge.validate_drc(source, candidate)
    checks = result["checks"]
    checks["source_unconnected_126"] = checks.pop("source_unconnected_141")
    checks["candidate_unconnected_124"] = checks.pop("candidate_unconnected_139")
    if not all(checks.values()):
        raise FinalRebaseError("R8c DRC gate contains a false check")
    return result


def r8c_json_bytes(value: Mapping[str, Any]) -> bytes:
    if isinstance(value, dict):
        state_name = value.get("state")
        if state_name == "R8_EPD_EDGE_ACCESS_CANDIDATE_HOLD":
            value["state"] = "R8C_EPD_INTERNAL_DCDC_PG_EDGE_ACCESS_CANDIDATE_HOLD"
            value["epd_source_modified"] = False
            value["r8a_internal_source_modified"] = False
            value["dcdc_pg_source_modified"] = False
            value["builder"]["r8b_edge_engine"] = {
                "path": str(R8B_EDGE_ENGINE.resolve()),
                "sha256": R8B_EDGE_ENGINE_SHA256,
            }
            value["builder"]["dcdc_route_builder"] = {
                "path": str(DCDC_ROUTE_BUILDER.resolve()),
                "sha256": DCDC_ROUTE_BUILDER_SHA256,
            }
            value["holds"] = [
                "J6 connector choice, pack envelope, and /BAT_POS-GND-/BAT_NTC line-order authority remain HOLD",
                "J5 enclosure cutout/cable envelope and SW1-SW5 pushrod travel remain HOLD",
                "12 U1 0.20 mm thermal drills, the inherited /EPD_SW_3V3 dangling endpoint, and 124 remaining unconnected items remain HOLD",
                "stackup/USB impedance, enclosure, assembly, thermal, RF, and manufacturing release remain HOLD",
            ]
        elif state_name == "R8_EPD_EDGE_ACCESS_BUILD_FAILED_HOLD":
            value["state"] = "R8C_EPD_INTERNAL_DCDC_PG_EDGE_ACCESS_BUILD_FAILED_HOLD"
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def main() -> int:
    configure()
    return r8.main()


if __name__ == "__main__":
    raise SystemExit(main())
