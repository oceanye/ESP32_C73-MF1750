#!/usr/bin/env python3
"""Build the unified staging-only R8b EPD + internal + edge candidate.

The frozen input is the DRC-clean R8a internal-control candidate.  This
wrapper binds the already-proven edge-access mutation engine to that source
and adds independent UUID/geometry proofs for both inherited additive route
sets: 102 EPD/MCU copper objects and 5 /USB_INPUT_VALID_N copper objects.
No formal project file is an output.
"""

from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import build_mf1750_wroom_b3_r8_epd_edge_access as r8


edge = r8.edge
pcbnew = r8.pcbnew

ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8a_internal_control_routed.kicad_pcb"
SOURCE_BOARD_SHA256 = (
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
R8_REBASE_ENGINE = HARDWARE / "build_mf1750_wroom_b3_r8_epd_edge_access.py"
R8_REBASE_ENGINE_SHA256 = (
    "58f9857151a1491132c0e2ffc6771d4046a2451d47071de4751e5c23e11f92d2"
)
R8A_ROUTE_REPORT = STAGING / "r8a_internal_control_route_report.json"
R8A_ROUTE_REPORT_SHA256 = (
    "1cd86a48acbd46661972cc4ee53411bd367186c1747241e6b0a69aa4071cb4bb"
)
R8A_ROUTE_BUILDER = HARDWARE / "route_mf1750_wroom_b3_internal_control_r8.py"
R8A_ROUTE_BUILDER_SHA256 = (
    "79f50adead4a36135f4cd5a9f4fe4dd726d135e2b9bc7af99b974795ad6fd0bd"
)

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8b_epd_internal_edge_access.kicad_pcb"
OUTPUT_REPORT = STAGING / "r8b_epd_internal_edge_access_report.json"
OUTPUT_DRC = STAGING / "r8b_epd_internal_edge_access_drc.json"
PREVIEW_DIR = STAGING / "r8b_epd_internal_edge_access_preview"
OUTPUT_TOP = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8b_epd_internal_edge_access_top.png"
OUTPUT_BOTTOM = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8b_epd_internal_edge_access_bottom.png"

EXPECTED_SOURCE_COPPER = 1222
EXPECTED_CANDIDATE_COPPER = 1222
EXPECTED_SOURCE_UNCONNECTED = 127
EXPECTED_CANDIDATE_UNCONNECTED = 125
EXPECTED_EPD_COPPER = 102
EXPECTED_INTERNAL_COPPER = 5
EXPECTED_INTERNAL_NET = "/USB_INPUT_VALID_N"


class UnifiedError(r8.RebaseError):
    """Fail-closed unified-route preservation error."""


def configure() -> None:
    protected = dict(r8.PROTECTED_HASHES)
    protected.pop(r8.SOURCE_BOARD, None)
    protected[SOURCE_BOARD] = SOURCE_BOARD_SHA256
    protected[EPD_BOARD] = EPD_BOARD_SHA256
    protected[HYGIENE_BOARD] = HYGIENE_BOARD_SHA256
    protected[R8_REBASE_ENGINE] = R8_REBASE_ENGINE_SHA256
    protected[R8A_ROUTE_REPORT] = R8A_ROUTE_REPORT_SHA256
    protected[R8A_ROUTE_BUILDER] = R8A_ROUTE_BUILDER_SHA256

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

    r8.epd_route_preservation = combined_route_preservation
    r8.validate_r8_drc = validate_r8b_drc
    r8.json_bytes = r8b_json_bytes


def state(path: Path) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    board = pcbnew.LoadBoard(str(path.resolve()))
    if board is None:
        raise UnifiedError(f"could not load copper-audit board: {path}")
    signatures = edge.board_state(board)["tracks"]
    objects = {edge.item_uuid(item): item for item in board.GetTracks()}
    return board, signatures, objects


def digest(values: Mapping[str, Any]) -> str:
    payload = json.dumps(
        sorted((uuid, signature) for uuid, signature in values.items()),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def kind_counts(objects: Mapping[str, Any]) -> dict[str, int]:
    counts = collections.Counter(
        "via" if isinstance(item, pcbnew.PCB_VIA) else "track"
        for item in objects.values()
    )
    return dict(sorted(counts.items()))


def net_counts(objects: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    result: dict[str, collections.Counter[str]] = {}
    for item in objects.values():
        kind = "via" if isinstance(item, pcbnew.PCB_VIA) else "track"
        result.setdefault(item.GetNetname(), collections.Counter())[kind] += 1
    return {
        net: dict(sorted(counts.items())) for net, counts in sorted(result.items())
    }


def combined_route_preservation(candidate_path: Path) -> dict[str, Any]:
    _, hygiene, _ = state(HYGIENE_BOARD)
    _, epd, _ = state(EPD_BOARD)
    _, source, source_objects = state(SOURCE_BOARD)
    _, candidate, _ = state(candidate_path)

    hygiene_ids = set(hygiene)
    epd_ids_all = set(epd)
    source_ids = set(source)
    candidate_ids = set(candidate)
    epd_added_ids = epd_ids_all - hygiene_ids
    internal_ids = source_ids - epd_ids_all
    source_non_vbus = source_ids - set(edge.SOURCE_USB_VBUS_TRACK_UUIDS)
    replacement_ids = candidate_ids - source_non_vbus
    epd_added_objects = {uuid: source_objects[uuid] for uuid in epd_added_ids}
    internal_objects = {uuid: source_objects[uuid] for uuid in internal_ids}

    def drift(ids: set[str], before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
        return sorted(
            uuid for uuid in ids if uuid not in after or before[uuid] != after[uuid]
        )

    hygiene_to_epd_drift = drift(hygiene_ids, hygiene, epd)
    epd_to_source_drift = drift(epd_ids_all, epd, source)
    epd_candidate_drift = drift(epd_added_ids, source, candidate)
    internal_candidate_drift = drift(internal_ids, source, candidate)
    all_retained_drift = drift(source_non_vbus, source, candidate)
    checks = {
        "hygiene_copper_count_1115": len(hygiene_ids) == 1115,
        "epd_source_copper_count_1217": len(epd_ids_all) == 1217,
        "r8a_source_copper_count_1222": len(source_ids) == EXPECTED_SOURCE_COPPER,
        "candidate_copper_count_1222": len(candidate_ids)
        == EXPECTED_CANDIDATE_COPPER,
        "hygiene_exact_subset_of_epd": hygiene_ids <= epd_ids_all
        and not hygiene_to_epd_drift,
        "epd_exact_subset_of_r8a": epd_ids_all <= source_ids
        and not epd_to_source_drift,
        "epd_additive_set_exactly_102": len(epd_added_ids) == EXPECTED_EPD_COPPER,
        "internal_additive_set_exactly_5": len(internal_ids)
        == EXPECTED_INTERNAL_COPPER,
        "internal_net_exactly_usb_input_valid_n": {
            item.GetNetname() for item in internal_objects.values()
        }
        == {EXPECTED_INTERNAL_NET},
        "internal_geometry_4_tracks_1_via": kind_counts(internal_objects)
        == {"track": 4, "via": 1},
        "all_102_epd_objects_preserved": not epd_candidate_drift,
        "all_5_internal_objects_preserved": not internal_candidate_drift,
        "all_source_non_vbus_objects_preserved": not all_retained_drift,
        "only_exact_eight_source_vbus_removed": not (
            set(edge.SOURCE_USB_VBUS_TRACK_UUIDS) & candidate_ids
        ),
        "exactly_eight_replacement_vbus_added": len(replacement_ids) == 8,
    }
    if not all(checks.values()):
        raise UnifiedError(
            "unified route-preservation gate failed: "
            + json.dumps(checks, ensure_ascii=False, sort_keys=True)
        )
    return {
        "passed": True,
        "checks": checks,
        "counts": {
            "hygiene": len(hygiene_ids),
            "epd_source": len(epd_ids_all),
            "r8a_source": len(source_ids),
            "candidate": len(candidate_ids),
        },
        "epd_102": {
            "count": len(epd_added_ids),
            "kind_counts": kind_counts(epd_added_objects),
            "by_net": net_counts(epd_added_objects),
            "uuid_signature_sha256": digest(
                {uuid: source[uuid] for uuid in epd_added_ids}
            ),
            "missing_or_changed": epd_candidate_drift,
        },
        "internal_5": {
            "count": len(internal_ids),
            "kind_counts": kind_counts(internal_objects),
            "by_net": net_counts(internal_objects),
            "uuid_signature_sha256": digest(
                {uuid: source[uuid] for uuid in internal_ids}
            ),
            "uuids": sorted(internal_ids),
            "missing_or_changed": internal_candidate_drift,
        },
        "other_retained_copper_drift": all_retained_drift,
        "replacement_vbus_uuids": sorted(replacement_ids),
    }


def validate_r8b_drc(
    source: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    result = edge.validate_drc(source, candidate)
    checks = result["checks"]
    checks["source_unconnected_127"] = checks.pop("source_unconnected_141")
    checks["candidate_unconnected_125"] = checks.pop("candidate_unconnected_139")
    if not all(checks.values()):
        raise UnifiedError("R8b DRC gate contains a false check")
    return result


def r8b_json_bytes(value: Mapping[str, Any]) -> bytes:
    if isinstance(value, dict):
        state_name = value.get("state")
        if state_name == "R8_EPD_EDGE_ACCESS_CANDIDATE_HOLD":
            value["state"] = "R8B_EPD_INTERNAL_EDGE_ACCESS_CANDIDATE_HOLD"
            value["epd_source_modified"] = False
            value["r8a_internal_source_modified"] = False
            value["builder"]["rebase_engine"] = {
                "path": str(R8_REBASE_ENGINE.resolve()),
                "sha256": R8_REBASE_ENGINE_SHA256,
            }
            value["holds"] = [
                "J6 connector choice, pack envelope, and /BAT_POS-GND-/BAT_NTC line-order authority remain HOLD",
                "J5 enclosure cutout/cable envelope and SW1-SW5 pushrod travel remain HOLD",
                "12 U1 0.20 mm thermal drills, the inherited /EPD_SW_3V3 dangling endpoint, and 125 remaining unconnected items remain HOLD",
                "stackup/USB impedance, enclosure, assembly, thermal, RF, and manufacturing release remain HOLD",
            ]
        elif state_name == "R8_EPD_EDGE_ACCESS_BUILD_FAILED_HOLD":
            value["state"] = "R8B_EPD_INTERNAL_EDGE_ACCESS_BUILD_FAILED_HOLD"
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def main() -> int:
    configure()
    return r8.main()


if __name__ == "__main__":
    raise SystemExit(main())
