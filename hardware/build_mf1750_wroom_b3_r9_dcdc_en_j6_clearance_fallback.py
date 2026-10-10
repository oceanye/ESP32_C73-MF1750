#!/usr/bin/env python3
"""Build the fail-closed R9 DCDC_EN + J6-clearance staging candidate.

The sole copper baseline is the frozen R8d /DCDC_EN routed candidate.  The
validated R8e /PS_HOLD partial route was considered for an exact-object merge,
but all eight of its deterministic UUIDs collide with different /DCDC_EN
objects in that baseline.  Exact insertion would therefore overwrite proven
copper, and UUID regeneration would no longer be an exact-object merge.  This
builder records that evidence and takes the explicitly approved fallback:

* preserve all 1,263 source copper objects exactly;
* do not add the conflicting /PS_HOLD partial objects; and
* move only unrouted J6 from (14.75, 120.00) to (13.75, 120.00) mm.

All outputs are staging-only.  Formal PCB, schematic, project, and README
files are SHA-bound read-only inputs and are never written.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Mapping

import build_mf1750_wroom_b3_r8d_j6_c49_hand_solder_clearance as j6c


r8 = j6c.r8
edge = j6c.edge
pcbnew = j6c.pcbnew
r8b = j6c.r8d.r8b

ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

ANCESTOR_BOARD = (
    STAGING
    / "mf1750_wroom_b3_power_tf_r8d_epd_internal_dcdc_pg_pwr_int_edge_access.kicad_pcb"
)
ANCESTOR_BOARD_SHA256 = (
    "9a0f1e309abe27cc8577404e2ef62a719ca7a39934553023c941bff5b5c62403"
)

DCDC_SOURCE = (
    STAGING / "mf1750_wroom_b3_power_tf_r8d_edge_dcdc_en_routed.kicad_pcb"
)
DCDC_SOURCE_SHA256 = (
    "0784823edb50fa642f38784ddc30b420ef7731447cc6920396dc7e5275365ada"
)
DCDC_BUILDER = HARDWARE / "route_mf1750_wroom_b3_edge_dcdc_en_r8d.py"
DCDC_BUILDER_SHA256 = (
    "3f2ce4a13cb7f595311de32b4299bc26c6a1603106087f8608f66c765d20a656"
)
DCDC_REPORT = STAGING / "r8d_edge_dcdc_en_route_report.json"
DCDC_REPORT_SHA256 = (
    "c75f09bb7c98e22064399a46dc863532de8677a59d07c1a2a1292546d7e96065"
)

PS_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8e_ps_hold_partial_routed.kicad_pcb"
PS_BOARD_SHA256 = (
    "86e9c10b87f35f7528dc09c60315f4d7e982c63bbb92f7bcf0b96f00891b9e9b"
)
PS_BUILDER = HARDWARE / "route_mf1750_wroom_b3_ps_hold_r8e.py"
PS_BUILDER_SHA256 = (
    "679bb2b6b592497464eeda095b56a2d3337d6bc417e24b1d23caa6e2b391c40c"
)
PS_REPORT = STAGING / "r8e_ps_hold_route_report.json"
PS_REPORT_SHA256 = (
    "302ac48a3c0bfe0490784a88c373621d179cb7d9015a60f7fc0e492e827c8f09"
)
J6_CLEARANCE_BUILDER = (
    HARDWARE / "build_mf1750_wroom_b3_r8d_j6_c49_hand_solder_clearance.py"
)
J6_CLEARANCE_BUILDER_SHA256 = (
    "d8f7b8c610b1598ec204f5475ab032b18c5ed5f7eb2a9c0d62d3a8b2236438e8"
)

OUTPUT_BOARD = (
    STAGING / "mf1750_wroom_b3_power_tf_r9_dcdc_en_j6_clearance_fallback.kicad_pcb"
)
OUTPUT_REPORT = STAGING / "r9_dcdc_en_j6_clearance_fallback_report.json"
OUTPUT_DRC = STAGING / "r9_dcdc_en_j6_clearance_fallback_drc.json"
PREVIEW_DIR = STAGING / "r9_dcdc_en_j6_clearance_fallback_preview"
OUTPUT_TOP = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r9_dcdc_en_j6_clearance_fallback_top.png"
OUTPUT_BOTTOM = (
    PREVIEW_DIR
    / "mf1750_wroom_b3_power_tf_r9_dcdc_en_j6_clearance_fallback_bottom.png"
)
OUTPUT_ISO = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r9_dcdc_en_j6_clearance_fallback_iso.png"

EXPECTED_SOURCE_COPPER = 1263
EXPECTED_CANDIDATE_COPPER = 1263
EXPECTED_UNCONNECTED = 120
EXPECTED_ANCESTOR_COPPER = 1238
EXPECTED_DCDC_ADDED = 25
EXPECTED_PS_ADDED = 8
DCDC_SIGNATURE_SHA256 = (
    "2857f9220eb6218749f4fbb4521ee81d3eb56eda3d36e7e8de2a6adfce717b28"
)
PS_SIGNATURE_SHA256 = (
    "58ffbe3899ab4ac9c2208b9e1822fda1d53a19c5bcc48cd7563531a3a462a805"
)
PS_UUIDS = frozenset(
    {
        "13286504-929c-48a5-bf61-8b3d5fc1b966",
        "31005013-4cbf-4796-8b78-e3fd444cf820",
        "4717ba1c-9950-47d8-9f31-ce667f5e9b3b",
        "5b6ea964-f382-4b7b-b62b-3a6e232607a8",
        "5e569e17-70a9-4933-bbfe-92a4c83c7319",
        "87e43223-0b2c-4302-839c-f444f6682e75",
        "b998de9a-ca3c-4d93-9608-55e2b411cf52",
        "c22a5de8-df05-4618-8517-519c914dad58",
    }
)


class R9Error(j6c.ClearanceError):
    """Fail-closed R9 merge/fallback error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def configure() -> None:
    """Bind the proven J6-only engine to the DCDC source and R9 outputs."""
    j6c.configure()
    protected = dict(r8.PROTECTED_HASHES)
    protected.update(
        {
            ANCESTOR_BOARD: ANCESTOR_BOARD_SHA256,
            DCDC_SOURCE: DCDC_SOURCE_SHA256,
            DCDC_BUILDER: DCDC_BUILDER_SHA256,
            DCDC_REPORT: DCDC_REPORT_SHA256,
            PS_BOARD: PS_BOARD_SHA256,
            PS_BUILDER: PS_BUILDER_SHA256,
            PS_REPORT: PS_REPORT_SHA256,
            J6_CLEARANCE_BUILDER: J6_CLEARANCE_BUILDER_SHA256,
        }
    )

    # The imported J6 engine resolves these globals at call time.
    j6c.SOURCE_BOARD = DCDC_SOURCE
    j6c.SOURCE_BOARD_SHA256 = DCDC_SOURCE_SHA256
    j6c.OUTPUT_BOARD = OUTPUT_BOARD
    j6c.OUTPUT_REPORT = OUTPUT_REPORT
    j6c.OUTPUT_DRC = OUTPUT_DRC
    j6c.PREVIEW_DIR = PREVIEW_DIR
    j6c.OUTPUT_TOP = OUTPUT_TOP
    j6c.OUTPUT_BOTTOM = OUTPUT_BOTTOM
    j6c.EXPECTED_COPPER = EXPECTED_SOURCE_COPPER
    j6c.EXPECTED_UNCONNECTED = EXPECTED_UNCONNECTED

    r8.SOURCE_BOARD = DCDC_SOURCE
    r8.SOURCE_BOARD_SHA256 = DCDC_SOURCE_SHA256
    r8.OUTPUT_BOARD = OUTPUT_BOARD
    r8.OUTPUT_REPORT = OUTPUT_REPORT
    r8.OUTPUT_DRC = OUTPUT_DRC
    r8.PREVIEW_DIR = PREVIEW_DIR
    r8.OUTPUT_TOP = OUTPUT_TOP
    r8.OUTPUT_BOTTOM = OUTPUT_BOTTOM
    r8.EXPECTED_SOURCE_COPPER = EXPECTED_SOURCE_COPPER
    r8.EXPECTED_CANDIDATE_COPPER = EXPECTED_CANDIDATE_COPPER
    r8.EXPECTED_SOURCE_UNCONNECTED = EXPECTED_UNCONNECTED
    r8.EXPECTED_CANDIDATE_UNCONNECTED = EXPECTED_UNCONNECTED
    r8.PROTECTED_HASHES = protected
    r8.__file__ = str(Path(__file__).resolve())

    j6c.preservation_audit = preservation_audit
    edge.build_once = j6c.build_once
    edge.mechanical_evidence = j6c.mechanical_evidence
    r8.epd_route_preservation = route_provenance_and_merge_decision
    r8.validate_r8_drc = validate_drc
    r8.json_bytes = report_json_bytes


def changed_keys(before: Mapping[Any, Any], after: Mapping[Any, Any]) -> list[Any]:
    return sorted(
        key
        for key in set(before) | set(after)
        if key not in before or key not in after or before[key] != after[key]
    )


def preservation_audit(
    source: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    transform_changes = changed_keys(
        source["footprint_transform"], candidate["footprint_transform"]
    )
    checks = {
        "footprint_inventory_exact": set(source["footprint_transform"])
        == set(candidate["footprint_transform"]),
        "only_j6_transform_changed": transform_changes == ["J6"],
        "source_j6_transform_exact": source["footprint_transform"]["J6"]
        == j6c.transform_tuple(*j6c.SOURCE_J6),
        "candidate_j6_transform_exact": candidate["footprint_transform"]["J6"]
        == j6c.transform_tuple(*j6c.CANDIDATE_J6),
        "all_nontransform_footprint_data_exact": source["footprint_static"]
        == candidate["footprint_static"],
        "all_pad_local_data_exact": source["pads_local"] == candidate["pads_local"],
        "all_graphics_local_exact": source["graphics_local"]
        == candidate["graphics_local"],
        "all_fields_local_exact": source["fields_local"]
        == candidate["fields_local"],
        "all_children_exact": source["children"] == candidate["children"],
        "all_1263_copper_uuid_geometry_exact": len(source["tracks"])
        == EXPECTED_SOURCE_COPPER
        and source["tracks"] == candidate["tracks"],
        "all_zones_exact": source["zones"] == candidate["zones"],
        "all_drawings_exact": source["drawings"] == candidate["drawings"],
        "j4_j5_sw_edge_access_transforms_exact": all(
            source["footprint_transform"][reference]
            == candidate["footprint_transform"][reference]
            for reference in j6c.FROZEN_EDGE_REFS
        ),
    }
    if not all(checks.values()):
        raise R9Error(
            "R9 J6-only preservation gate failed: "
            + json.dumps(checks, ensure_ascii=False, sort_keys=True)
        )
    return {
        "passed": True,
        "checks": checks,
        "changed_footprint_transforms": transform_changes,
        "source_copper_count": len(source["tracks"]),
        "candidate_copper_count": len(candidate["tracks"]),
        "copper_signature_sha256": r8b.digest(source["tracks"]),
        "zones_count": len(source["zones"]),
        "drawings_count": len(source["drawings"]),
    }


def drift(
    identifiers: set[str], before: Mapping[str, Any], after: Mapping[str, Any]
) -> list[str]:
    return sorted(
        uuid
        for uuid in identifiers
        if uuid not in before or uuid not in after or before[uuid] != after[uuid]
    )


def as_json_signature(signature: Any) -> Any:
    if isinstance(signature, tuple):
        return [as_json_signature(item) for item in signature]
    return signature


def route_provenance_and_merge_decision(candidate_path: Path) -> dict[str, Any]:
    _, ancestor, ancestor_objects = r8b.state(ANCESTOR_BOARD)
    _, dcdc, dcdc_objects = r8b.state(DCDC_SOURCE)
    _, ps, ps_objects = r8b.state(PS_BOARD)
    _, candidate, _ = r8b.state(candidate_path)

    ancestor_ids = set(ancestor)
    dcdc_ids = set(dcdc) - ancestor_ids
    ps_ids = set(ps) - ancestor_ids
    collisions = dcdc_ids & ps_ids
    collision_signature_differences = sorted(
        uuid for uuid in collisions if dcdc[uuid] != ps[uuid]
    )
    dcdc_added_objects = {uuid: dcdc_objects[uuid] for uuid in dcdc_ids}
    ps_added_objects = {uuid: ps_objects[uuid] for uuid in ps_ids}
    collision_evidence = [
        {
            "uuid": uuid,
            "dcdc_signature": as_json_signature(dcdc[uuid]),
            "ps_hold_signature": as_json_signature(ps[uuid]),
        }
        for uuid in sorted(collisions)
    ]

    dcdc_report = json.loads(DCDC_REPORT.read_text(encoding="utf-8"))
    ps_report = json.loads(PS_REPORT.read_text(encoding="utf-8"))
    dcdc_verifier = dcdc_report.get("board_verifier", {}).get("summary", {})
    ps_verifier = ps_report.get("board_verifier", {}).get("summary", {})

    checks = {
        "ancestor_count_1238": len(ancestor_ids) == EXPECTED_ANCESTOR_COPPER,
        "dcdc_source_count_1263": len(dcdc) == EXPECTED_SOURCE_COPPER,
        "ps_source_count_1246": len(ps) == EXPECTED_ANCESTOR_COPPER
        + EXPECTED_PS_ADDED,
        "candidate_count_1263": len(candidate) == EXPECTED_CANDIDATE_COPPER,
        "ancestor_exact_subset_of_dcdc": ancestor_ids <= set(dcdc)
        and not drift(ancestor_ids, ancestor, dcdc),
        "ancestor_exact_subset_of_ps": ancestor_ids <= set(ps)
        and not drift(ancestor_ids, ancestor, ps),
        "candidate_copper_exactly_dcdc_source": candidate == dcdc,
        "dcdc_added_exactly_25": len(dcdc_ids) == EXPECTED_DCDC_ADDED,
        "dcdc_added_20_tracks_5_vias": r8b.kind_counts(dcdc_added_objects)
        == {"track": 20, "via": 5},
        "dcdc_added_net_only": set(
            item.GetNetname() for item in dcdc_added_objects.values()
        )
        == {"/DCDC_EN"},
        "dcdc_signature_exact": r8b.digest(
            {uuid: dcdc[uuid] for uuid in dcdc_ids}
        )
        == DCDC_SIGNATURE_SHA256,
        "ps_added_exactly_8": len(ps_ids) == EXPECTED_PS_ADDED,
        "ps_uuid_set_exact": ps_ids == set(PS_UUIDS),
        "ps_added_6_tracks_2_vias": r8b.kind_counts(ps_added_objects)
        == {"track": 6, "via": 2},
        "ps_added_net_only": set(
            item.GetNetname() for item in ps_added_objects.values()
        )
        == {"/PS_HOLD"},
        "ps_signature_exact": r8b.digest({uuid: ps[uuid] for uuid in ps_ids})
        == PS_SIGNATURE_SHA256,
        "all_8_ps_uuids_collide_with_dcdc": collisions == set(PS_UUIDS),
        "all_8_collision_signatures_differ": collision_signature_differences
        == sorted(PS_UUIDS),
        "ps_partial_exact_objects_absent_from_candidate": all(
            uuid in candidate and candidate[uuid] == dcdc[uuid] and candidate[uuid] != ps[uuid]
            for uuid in PS_UUIDS
        ),
        "dcdc_report_state_exact": dcdc_report.get("state")
        == "R8D_EDGE_DCDC_EN_ROUTED_CANDIDATE",
        "dcdc_report_output_hash_exact": dcdc_report.get("output", {}).get(
            "sha256"
        )
        == DCDC_SOURCE_SHA256,
        "dcdc_report_drc_passed": dcdc_report.get("drc_gate", {}).get("passed")
        is True,
        "dcdc_report_verifier_13_of_13": dcdc_verifier
        == {"failed": 0, "passed": 13, "total": 13},
        "ps_report_state_exact": ps_report.get("state")
        == "R8E_PS_HOLD_PARTIAL_ROUTE_HOLD",
        "ps_report_output_hash_exact": ps_report.get("output", {}).get("sha256")
        == PS_BOARD_SHA256,
        "ps_report_safety_passed": ps_report.get("drc_gate", {}).get(
            "safety_passed"
        )
        is True,
        "ps_report_verifier_13_of_13": ps_verifier
        == {"failed": 0, "passed": 13, "total": 13},
    }
    if not all(checks.values()):
        raise R9Error(
            "R9 route provenance/fallback gate failed: "
            + json.dumps(checks, ensure_ascii=False, sort_keys=True)
        )

    return {
        "passed": True,
        "checks": checks,
        "merge_decision": "PS_PARTIAL_EXCLUDED_UUID_COLLISION",
        "fallback_selected": True,
        "ps_hold_partial_included": False,
        "exact_merge_possible": False,
        "reason": (
            "all eight validated PS_HOLD object UUIDs are already occupied by "
            "different DCDC_EN copper; exact insertion would overwrite proven "
            "DCDC copper and UUID regeneration would not be an exact-object merge"
        ),
        "ancestor": {
            "path": str(ANCESTOR_BOARD.resolve()),
            "sha256": ANCESTOR_BOARD_SHA256,
            "copper_count": len(ancestor),
        },
        "dcdc_source": {
            "path": str(DCDC_SOURCE.resolve()),
            "sha256": DCDC_SOURCE_SHA256,
            "builder": {
                "path": str(DCDC_BUILDER.resolve()),
                "sha256": DCDC_BUILDER_SHA256,
            },
            "report": {
                "path": str(DCDC_REPORT.resolve()),
                "sha256": DCDC_REPORT_SHA256,
            },
            "added_count": len(dcdc_ids),
            "added_signature_sha256": DCDC_SIGNATURE_SHA256,
        },
        "ps_hold_partial": {
            "path": str(PS_BOARD.resolve()),
            "sha256": PS_BOARD_SHA256,
            "builder": {
                "path": str(PS_BUILDER.resolve()),
                "sha256": PS_BUILDER_SHA256,
            },
            "report": {
                "path": str(PS_REPORT.resolve()),
                "sha256": PS_REPORT_SHA256,
            },
            "added_count": len(ps_ids),
            "added_signature_sha256": PS_SIGNATURE_SHA256,
            "added_uuids": sorted(ps_ids),
        },
        "uuid_collision_count": len(collisions),
        "uuid_collisions": collision_evidence,
        "candidate_copper_count": len(candidate),
    }


def validate_drc(
    source: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    source_identity = edge.violation_identity(source)
    candidate_identity = edge.violation_identity(candidate)
    source_nets = edge.unconnected_by_net(source)
    candidate_nets = edge.unconnected_by_net(candidate)
    delta = {
        net: candidate_nets.get(net, 0) - source_nets.get(net, 0)
        for net in sorted(set(source_nets) | set(candidate_nets))
        if source_nets.get(net, 0) != candidate_nets.get(net, 0)
    }
    source_drills = {
        uuid
        for category, uuids in source_identity
        if category == "drill_out_of_range"
        for uuid in uuids
    }
    source_dangling = {
        uuid
        for category, uuids in source_identity
        if category == "track_dangling"
        for uuid in uuids
    }
    checks = {
        "source_categories_exact": source["violation_categories"]
        == edge.EXPECTED_DRC_CATEGORIES,
        "candidate_categories_exact": candidate["violation_categories"]
        == edge.EXPECTED_DRC_CATEGORIES,
        "source_violation_count_13": source["violation_count"] == 13,
        "candidate_violation_count_13": candidate["violation_count"] == 13,
        "source_unconnected_120": source["unconnected_count"]
        == EXPECTED_UNCONNECTED,
        "candidate_unconnected_120": candidate["unconnected_count"]
        == EXPECTED_UNCONNECTED,
        "unconnected_by_net_exactly_unchanged": not delta,
        "dcdc_en_ratline_zero": source_nets.get("/DCDC_EN", 0) == 0
        and candidate_nets.get("/DCDC_EN", 0) == 0,
        "ps_hold_ratline_remains_two": source_nets.get("/PS_HOLD", 0) == 2
        and candidate_nets.get("/PS_HOLD", 0) == 2,
        "usb_vbus_ratline_zero": source_nets.get("/USB_VBUS", 0) == 0
        and candidate_nets.get("/USB_VBUS", 0) == 0,
        "pwr_int_n_ratline_zero": source_nets.get("/PWR_INT_N", 0) == 0
        and candidate_nets.get("/PWR_INT_N", 0) == 0,
        "source_parity_zero": source["schematic_parity_count"] == 0,
        "candidate_parity_zero": candidate["schematic_parity_count"] == 0,
        "violation_identity_exactly_unchanged": source_identity
        == candidate_identity,
        "source_u1_drill_uuid_set_exact": source_drills
        == set(edge.r7base.U1_DRILL_UUIDS),
        "source_dangling_uuid_exact": source_dangling
        == {edge.r7base.DANGLING_TRACK_UUID},
    }
    if not all(checks.values()):
        raise R9Error(
            "R9 DRC/connectivity gate failed: "
            + json.dumps(checks, ensure_ascii=False, sort_keys=True)
        )
    return {
        "passed": True,
        "checks": checks,
        "source_categories": source["violation_categories"],
        "candidate_categories": candidate["violation_categories"],
        "source_violation_identity": [
            [category, list(uuids)] for category, uuids in source_identity
        ],
        "candidate_violation_identity": [
            [category, list(uuids)] for category, uuids in candidate_identity
        ],
        "source_unconnected_by_net": source_nets,
        "candidate_unconnected_by_net": candidate_nets,
        "unconnected_delta_by_net": delta,
        "unconnected_count": candidate["unconnected_count"],
        "schematic_parity_count": candidate["schematic_parity_count"],
    }


def report_json_bytes(value: Mapping[str, Any]) -> bytes:
    if isinstance(value, dict):
        state = value.get("state")
        if state in {
            "R8_EPD_EDGE_ACCESS_CANDIDATE_HOLD",
            "R9_DCDC_EN_J6_CLEARANCE_PS_HOLD_EXCLUDED_CANDIDATE_HOLD",
        }:
            value["state"] = (
                "R9_DCDC_EN_J6_CLEARANCE_PS_HOLD_EXCLUDED_CANDIDATE_HOLD"
            )
            value["overall_status"] = "HOLD"
            value["fallback_selected"] = True
            value["ps_hold_partial_included"] = False
            value["dcdc_source_modified"] = False
            value["builder"]["dcdc_route_builder"] = {
                "path": str(DCDC_BUILDER.resolve()),
                "sha256": DCDC_BUILDER_SHA256,
            }
            value["builder"]["dcdc_route_report"] = {
                "path": str(DCDC_REPORT.resolve()),
                "sha256": DCDC_REPORT_SHA256,
            }
            value["builder"]["ps_hold_partial_builder"] = {
                "path": str(PS_BUILDER.resolve()),
                "sha256": PS_BUILDER_SHA256,
                "included": False,
            }
            value["builder"]["ps_hold_partial_report"] = {
                "path": str(PS_REPORT.resolve()),
                "sha256": PS_REPORT_SHA256,
                "included": False,
            }
            evidence = value.get("connectivity_evidence", {})
            if isinstance(evidence, dict):
                evidence["unconnected_reduction"] = {
                    "source_total": EXPECTED_UNCONNECTED,
                    "candidate_total": EXPECTED_UNCONNECTED,
                    "delta_by_net": {},
                    "reason": (
                        "J6-only unrouted-footprint translation preserves all "
                        "ratlines; conflicting PS_HOLD exact objects were excluded"
                    ),
                    "all_net_ratline_counts_unchanged": True,
                    "dcdc_en_remaining": 0,
                    "ps_hold_remaining": 2,
                }
                evidence["usb_vbus_conclusion"] = (
                    "CONNECTED_SET_EXACTLY_PRESERVED_BY_J6_ONLY_MOVE"
                )
            value["holds"] = [
                "The validated PS_HOLD partial is deliberately excluded because all eight exact UUIDs collide with different proven DCDC_EN objects; PS_HOLD remains at two ratlines",
                "J6 placement clearance passes, but connector choice, battery-pack envelope, mating access, and BAT+/GND/NTC authority remain HOLD",
                "J5 enclosure cutout/cable envelope and SW1-SW5 pushrod travel remain HOLD",
                "12 U1 0.20 mm thermal drills, the inherited EPD_SW_3V3 dangling endpoint, and 120 remaining unconnected items remain HOLD",
                "stackup/USB impedance, enclosure, assembly, thermal, RF, and manufacturing release remain HOLD",
            ]
        elif state == "R8_EPD_EDGE_ACCESS_BUILD_FAILED_HOLD":
            value["state"] = "R9_DCDC_EN_J6_CLEARANCE_FALLBACK_BUILD_FAILED_HOLD"
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def render_isometric_and_bind_report() -> dict[str, Any]:
    protected_before = edge.protected_hashes()
    with tempfile.TemporaryDirectory(prefix="mf1750-r9-iso-") as name:
        temp_dir = Path(name)
        outputs = [temp_dir / "iso1.png", temp_dir / "iso2.png"]
        commands: list[list[str]] = []
        payloads: list[bytes] = []
        for output in outputs:
            command = [
                str(edge.KICAD_CLI.resolve()),
                "pcb",
                "render",
                "--side",
                "top",
                "--background",
                "opaque",
                "--quality",
                "high",
                "--width",
                "1800",
                "--height",
                "1600",
                "--perspective",
                "--floor",
                # KiCad's CLI parser treats a leading-negative rotate value as
                # another option on Windows; 315 degrees is exactly -45.
                "--rotate",
                "315,0,45",
                "--output",
                str(output.resolve()),
                str(OUTPUT_BOARD.resolve()),
            ]
            result = subprocess.run(
                command,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0 or not output.is_file():
                raise R9Error(
                    "isometric render failed: "
                    + json.dumps(
                        {
                            "returncode": result.returncode,
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                        },
                        ensure_ascii=False,
                    )
                )
            commands.append(command)
            payloads.append(output.read_bytes())
        iso_identical = payloads[0] == payloads[1]
        # KiCad's ray-traced raster can vary byte-for-byte between otherwise
        # identical invocations.  This image is visual evidence only; the PCB
        # itself remains subject to the strict byte-identical double-build
        # release gate above.  Preserve both hashes rather than disguising the
        # renderer behaviour as a board failure.
        iso_payload = payloads[0]

    if edge.protected_hashes() != protected_before:
        raise R9Error("protected input changed during isometric rendering")
    edge.r7base.atomic_write_bytes(OUTPUT_ISO, iso_payload)
    report = json.loads(OUTPUT_REPORT.read_text(encoding="utf-8"))
    iso_record = {
        "path": str(OUTPUT_ISO.resolve()),
        "bytes": len(iso_payload),
        "sha256": hashlib.sha256(iso_payload).hexdigest(),
        "render": "perspective_isometric_top_315_0_45_equivalent_to_-45_0_45",
    }
    report["artifacts"]["isometric_3d"] = iso_record
    report["determinism"]["isometric_3d"] = {
        "byte_identical": iso_identical,
        "release_gate": False,
        "classification": "VISUAL_EVIDENCE_ONLY_NOT_A_PCB_DETERMINISM_GATE",
        "run1_sha256": hashlib.sha256(payloads[0]).hexdigest(),
        "run2_sha256": hashlib.sha256(payloads[1]).hexdigest(),
        "run1_bytes": len(iso_payload),
        "run2_bytes": len(iso_payload),
        "commands": commands,
    }
    report["visual_review_inputs"] = {
        "top": str(OUTPUT_TOP.resolve()),
        "bottom": str(OUTPUT_BOTTOM.resolve()),
        "isometric_3d": str(OUTPUT_ISO.resolve()),
        "review_status": "GENERATED_FOR_AGENT_VISUAL_REVIEW",
    }
    report_payload = report_json_bytes(report)
    edge.r7base.atomic_write_bytes(OUTPUT_REPORT, report_payload)
    if sha256_file(OUTPUT_ISO) != iso_record["sha256"]:
        raise R9Error("published isometric hash differs")
    if edge.protected_hashes() != protected_before:
        raise R9Error("protected input changed during report binding")
    return iso_record


def main() -> int:
    configure()
    result = r8.main()
    if result == 0 and "--check-only" not in sys.argv[1:]:
        iso = render_isometric_and_bind_report()
        sys.stdout.write(
            json.dumps({"isometric_3d": iso}, ensure_ascii=False, indent=2)
            + "\n"
        )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
