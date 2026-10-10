#!/usr/bin/env python3
"""Build staging R8d EPD + internal + DCDC_PG + PWR_INT_N + edge candidate.

The SHA-frozen PWR_INT_N routed board is the sole PCB source.  The mutation
remains the proven edge-access whitelist.  Independent subset-chain audits
preserve the 102 EPD/MCU, 5 internal-control, 7 DCDC_PG, and 9 PWR_INT_N
additive copper objects by UUID and exact geometry.  No formal project
artifact is written.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import build_mf1750_wroom_b3_r8c_epd_internal_dcdc_pg_edge_access as r8c


r8b = r8c.r8b
r8 = r8c.r8
edge = r8c.edge

ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8c_pwr_int_n_routed.kicad_pcb"
SOURCE_BOARD_SHA256 = (
    "6a01299c8f64206f3c4fb540778ec9ad8f01fdc167e8c4c8f1b59016c10d0f1c"
)
DCDC_BOARD = r8c.SOURCE_BOARD
DCDC_BOARD_SHA256 = r8c.SOURCE_BOARD_SHA256
R8A_BOARD = r8c.R8A_BOARD
R8A_BOARD_SHA256 = r8c.R8A_BOARD_SHA256
EPD_BOARD = r8c.EPD_BOARD
EPD_BOARD_SHA256 = r8c.EPD_BOARD_SHA256
HYGIENE_BOARD = r8c.HYGIENE_BOARD
HYGIENE_BOARD_SHA256 = r8c.HYGIENE_BOARD_SHA256

R8C_EDGE_ENGINE = (
    HARDWARE / "build_mf1750_wroom_b3_r8c_epd_internal_dcdc_pg_edge_access.py"
)
R8C_EDGE_ENGINE_SHA256 = (
    "42a4547338a59de3ffa0d2eceae159948ce3fca92ff9c3d46d5bbe50a9732423"
)
PWR_ROUTE_BUILDER = HARDWARE / "route_mf1750_wroom_b3_pwr_int_n_r8c.py"
PWR_ROUTE_BUILDER_SHA256 = (
    "f8ec248974a1d89402ee9947707240862cd2e17ed29f08e0984588bdf51ac003"
)
PWR_ROUTE_REPORT = STAGING / "r8c_pwr_int_n_route_report.json"
PWR_ROUTE_REPORT_SHA256 = (
    "a7691fdcb865465153c91b65bcc99c72d7a0be4f73b3625ae3539449b2ec65d2"
)

OUTPUT_BOARD = (
    STAGING
    / "mf1750_wroom_b3_power_tf_r8d_epd_internal_dcdc_pg_pwr_int_edge_access.kicad_pcb"
)
OUTPUT_REPORT = STAGING / "r8d_epd_internal_dcdc_pg_pwr_int_edge_access_report.json"
OUTPUT_DRC = STAGING / "r8d_epd_internal_dcdc_pg_pwr_int_edge_access_drc.json"
PREVIEW_DIR = STAGING / "r8d_epd_internal_dcdc_pg_pwr_int_edge_access_preview"
OUTPUT_TOP = (
    PREVIEW_DIR
    / "mf1750_wroom_b3_power_tf_r8d_epd_internal_dcdc_pg_pwr_int_edge_access_top.png"
)
OUTPUT_BOTTOM = (
    PREVIEW_DIR
    / "mf1750_wroom_b3_power_tf_r8d_epd_internal_dcdc_pg_pwr_int_edge_access_bottom.png"
)

EXPECTED_SOURCE_COPPER = 1238
EXPECTED_CANDIDATE_COPPER = 1238
EXPECTED_SOURCE_UNCONNECTED = 125
EXPECTED_CANDIDATE_UNCONNECTED = 123
ROOT_README = ROOT / "README.md"
ROOT_README_SHA256 = (
    "bb5a241da9813327804e4df0159e6ba693d28e99f264812d52b1a19cf43a5663"
)
PWR_INT_N_UUIDS = frozenset(
    {
        "c7776b1c-df30-4261-89de-f5f6690b10b8",
        "3776a726-f742-492b-959e-f6200ff9e483",
        "2821dbea-7a56-40f1-bbaa-636e0b69d2fb",
        "556fcde1-492c-4762-ae77-b8390b692973",
        "aeefe90f-4422-4e53-a10f-aa256c8e5d75",
        "d1e143b2-3f25-4b94-83c5-be40f2f8ec01",
        "c3e3d35f-4d21-489e-a371-714ad0eb222c",
        "b81bb21b-4769-4b50-a2db-daab8727f26e",
        "37c0b706-33df-4ebf-badf-51766aeaa09b",
    }
)
PWR_INT_N_SIGNATURE_SHA256 = (
    "00b9920beb9dc179c6d99b79811f01c31710cb9a47ab1cced16ecc45e42a8813"
)


class FinalRebaseError(r8c.FinalRebaseError):
    """Fail-closed R8d route-chain preservation error."""


def configure() -> None:
    r8c.configure()
    protected = dict(r8.PROTECTED_HASHES)
    protected[SOURCE_BOARD] = SOURCE_BOARD_SHA256
    protected[DCDC_BOARD] = DCDC_BOARD_SHA256
    protected[R8A_BOARD] = R8A_BOARD_SHA256
    protected[EPD_BOARD] = EPD_BOARD_SHA256
    protected[HYGIENE_BOARD] = HYGIENE_BOARD_SHA256
    protected[R8C_EDGE_ENGINE] = R8C_EDGE_ENGINE_SHA256
    protected[PWR_ROUTE_BUILDER] = PWR_ROUTE_BUILDER_SHA256
    protected[PWR_ROUTE_REPORT] = PWR_ROUTE_REPORT_SHA256
    # Also freeze the repository README recorded by the approved PWR_INT_N
    # route report.  The board-family README remains protected by R8c.
    protected[ROOT_README] = ROOT_README_SHA256

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
    r8.validate_r8_drc = validate_r8d_drc
    r8.json_bytes = r8d_json_bytes


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
    _, dcdc, _ = r8b.state(DCDC_BOARD)
    _, source, source_objects = r8b.state(SOURCE_BOARD)
    _, candidate, _ = r8b.state(candidate_path)

    hygiene_ids = set(hygiene)
    epd_ids_all = set(epd)
    r8a_ids = set(r8a)
    dcdc_ids_all = set(dcdc)
    source_ids = set(source)
    candidate_ids = set(candidate)
    epd_ids = epd_ids_all - hygiene_ids
    internal_ids = r8a_ids - epd_ids_all
    dcdc_ids = dcdc_ids_all - r8a_ids
    pwr_ids = source_ids - dcdc_ids_all
    source_non_vbus = source_ids - set(edge.SOURCE_USB_VBUS_TRACK_UUIDS)
    replacement_ids = candidate_ids - source_non_vbus

    epd_objects = {uuid: source_objects[uuid] for uuid in epd_ids}
    internal_objects = {uuid: source_objects[uuid] for uuid in internal_ids}
    dcdc_objects = {uuid: source_objects[uuid] for uuid in dcdc_ids}
    pwr_objects = {uuid: source_objects[uuid] for uuid in pwr_ids}

    hygiene_epd_drift = drift(hygiene_ids, hygiene, epd)
    epd_r8a_drift = drift(epd_ids_all, epd, r8a)
    r8a_dcdc_drift = drift(r8a_ids, r8a, dcdc)
    dcdc_source_drift = drift(dcdc_ids_all, dcdc, source)
    epd_candidate_drift = drift(epd_ids, source, candidate)
    internal_candidate_drift = drift(internal_ids, source, candidate)
    dcdc_candidate_drift = drift(dcdc_ids, source, candidate)
    pwr_candidate_drift = drift(pwr_ids, source, candidate)
    retained_drift = drift(source_non_vbus, source, candidate)

    checks = {
        "hygiene_count_1115": len(hygiene_ids) == 1115,
        "epd_source_count_1217": len(epd_ids_all) == 1217,
        "r8a_source_count_1222": len(r8a_ids) == 1222,
        "dcdc_source_count_1229": len(dcdc_ids_all) == 1229,
        "pwr_source_count_1238": len(source_ids) == EXPECTED_SOURCE_COPPER,
        "candidate_count_1238": len(candidate_ids) == EXPECTED_CANDIDATE_COPPER,
        "hygiene_exact_subset_of_epd": hygiene_ids <= epd_ids_all
        and not hygiene_epd_drift,
        "epd_exact_subset_of_r8a": epd_ids_all <= r8a_ids and not epd_r8a_drift,
        "r8a_exact_subset_of_dcdc": r8a_ids <= dcdc_ids_all
        and not r8a_dcdc_drift,
        "dcdc_exact_subset_of_pwr_source": dcdc_ids_all <= source_ids
        and not dcdc_source_drift,
        "epd_set_exactly_102": len(epd_ids) == 102,
        "internal_set_exactly_5": len(internal_ids) == 5,
        "dcdc_pg_set_exactly_7": len(dcdc_ids) == 7,
        "pwr_int_n_set_exactly_9": len(pwr_ids) == 9,
        "pwr_int_n_uuid_set_exact": pwr_ids == set(PWR_INT_N_UUIDS),
        "epd_geometry_74_tracks_28_vias": r8b.kind_counts(epd_objects)
        == {"track": 74, "via": 28},
        "internal_geometry_4_tracks_1_via": r8b.kind_counts(internal_objects)
        == {"track": 4, "via": 1},
        "dcdc_geometry_5_tracks_2_vias": r8b.kind_counts(dcdc_objects)
        == {"track": 5, "via": 2},
        "pwr_geometry_7_tracks_2_vias": r8b.kind_counts(pwr_objects)
        == {"track": 7, "via": 2},
        "internal_net_exact": {
            item.GetNetname() for item in internal_objects.values()
        }
        == {"/USB_INPUT_VALID_N"},
        "dcdc_pg_net_exact": {
            item.GetNetname() for item in dcdc_objects.values()
        }
        == {"/DCDC_PG"},
        "pwr_int_n_net_exact": {
            item.GetNetname() for item in pwr_objects.values()
        }
        == {"/PWR_INT_N"},
        "pwr_int_n_signature_exact": r8b.digest(
            {uuid: source[uuid] for uuid in pwr_ids}
        )
        == PWR_INT_N_SIGNATURE_SHA256,
        "all_102_epd_preserved": not epd_candidate_drift,
        "all_5_internal_preserved": not internal_candidate_drift,
        "all_7_dcdc_pg_preserved": not dcdc_candidate_drift,
        "all_9_pwr_int_n_preserved": not pwr_candidate_drift,
        "all_source_non_vbus_preserved": not retained_drift,
        "source_non_vbus_count_1230": len(source_non_vbus) == 1230,
        "only_exact_eight_source_vbus_removed": not (
            set(edge.SOURCE_USB_VBUS_TRACK_UUIDS) & candidate_ids
        ),
        "exactly_eight_replacement_vbus_added": len(replacement_ids) == 8,
    }
    if not all(checks.values()):
        raise FinalRebaseError(
            "R8d route-chain preservation failed: "
            + json.dumps(checks, ensure_ascii=False, sort_keys=True)
        )

    def group(
        ids: set[str], objects: Mapping[str, Any], missing: list[str]
    ) -> dict[str, Any]:
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
            "dcdc_source": len(dcdc_ids_all),
            "pwr_source": len(source_ids),
            "candidate": len(candidate_ids),
        },
        "epd_102": group(epd_ids, epd_objects, epd_candidate_drift),
        "internal_5": group(
            internal_ids, internal_objects, internal_candidate_drift
        ),
        "dcdc_pg_7": group(dcdc_ids, dcdc_objects, dcdc_candidate_drift),
        "pwr_int_n_9": group(pwr_ids, pwr_objects, pwr_candidate_drift),
        "other_retained_copper_drift": retained_drift,
        "replacement_vbus_uuids": sorted(replacement_ids),
    }


def validate_r8d_drc(
    source: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    result = edge.validate_drc(source, candidate)
    checks = result["checks"]
    checks["source_unconnected_125"] = checks.pop("source_unconnected_141")
    checks["candidate_unconnected_123"] = checks.pop("candidate_unconnected_139")
    if not all(checks.values()):
        raise FinalRebaseError("R8d DRC gate contains a false check")
    return result


def r8d_json_bytes(value: Mapping[str, Any]) -> bytes:
    if isinstance(value, dict):
        state_name = value.get("state")
        if state_name == "R8_EPD_EDGE_ACCESS_CANDIDATE_HOLD":
            value["state"] = (
                "R8D_EPD_INTERNAL_DCDC_PG_PWR_INT_EDGE_ACCESS_CANDIDATE_HOLD"
            )
            value["epd_source_modified"] = False
            value["r8a_internal_source_modified"] = False
            value["dcdc_pg_source_modified"] = False
            value["pwr_int_n_source_modified"] = False
            value["builder"]["r8c_edge_engine"] = {
                "path": str(R8C_EDGE_ENGINE.resolve()),
                "sha256": R8C_EDGE_ENGINE_SHA256,
            }
            value["builder"]["pwr_int_n_route_builder"] = {
                "path": str(PWR_ROUTE_BUILDER.resolve()),
                "sha256": PWR_ROUTE_BUILDER_SHA256,
            }
            value["builder"]["pwr_int_n_route_report"] = {
                "path": str(PWR_ROUTE_REPORT.resolve()),
                "sha256": PWR_ROUTE_REPORT_SHA256,
            }
            value["holds"] = [
                "J6 connector choice, pack envelope, and /BAT_POS-GND-/BAT_NTC line-order authority remain HOLD",
                "J5 enclosure cutout/cable envelope and SW1-SW5 pushrod travel remain HOLD",
                "12 U1 0.20 mm thermal drills, the inherited /EPD_SW_3V3 dangling endpoint, and 123 remaining unconnected items remain HOLD",
                "stackup/USB impedance, enclosure, assembly, thermal, RF, and manufacturing release remain HOLD",
            ]
        elif state_name == "R8_EPD_EDGE_ACCESS_BUILD_FAILED_HOLD":
            value["state"] = (
                "R8D_EPD_INTERNAL_DCDC_PG_PWR_INT_EDGE_ACCESS_BUILD_FAILED_HOLD"
            )
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def main() -> int:
    configure()
    return r8.main()


if __name__ == "__main__":
    raise SystemExit(main())
