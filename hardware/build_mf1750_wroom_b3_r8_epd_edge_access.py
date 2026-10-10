#!/usr/bin/env python3
"""Rebase the proven edge-access edits onto the frozen R7 EPD-routed board.

This builder writes only R8 staging artifacts.  Its PCB input is fixed by
SHA-256 and contains the already-verified EPD MCU routing.  The only PCB
changes are the same narrow edge-access mutations proven independently:

* rotate SW1..SW5 in place to 270 degrees;
* place J5 at (3.65, 108.70) mm / 270 degrees;
* place J6 at (14.75, 120.00) mm / 0 degrees;
* move the exact 28 newly edge-crossing F.SilkS shapes to F.Fab;
* give the exact four J5 GND pads a solid local zone connection; and
* replace the exact eight source /USB_VBUS tracks with eight deterministic
  F.Cu segments reaching the relocated J5 pads.

Every one of the source board's 1,217 copper objects is preserved by UUID and
geometry except those exact eight /USB_VBUS tracks.  A second audit proves the
102 EPD-route copper objects added over R7 hygiene remain byte-geometrically
identical.  Publication is fail-closed behind hashes, double-build identity,
DRC identity, per-net ratline evidence, schematic parity, and verifier 13/13.
The result remains a staging candidate, not a manufacturing release.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Iterable, Mapping

import build_mf1750_wroom_b3_r7_edge_access_probe as edge


pcbnew = edge.pcbnew

ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r7_epd_mcu_routed.kicad_pcb"
SOURCE_BOARD_SHA256 = (
    "adf3a61c2231049f4a50b6ba97d95d5bd7b7fe9ff54be3f27469eb3f78cdc009"
)
R7_HYGIENE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r7_drc_hygiene.kicad_pcb"
R7_HYGIENE_SHA256 = (
    "88dfc906bd8d15adccecc54ccdbb9a6d2e5f1ec3149ede199475923ba22c1cf8"
)
EDGE_ENGINE = HARDWARE / "build_mf1750_wroom_b3_r7_edge_access_probe.py"
EDGE_ENGINE_SHA256 = (
    "f49b2c4e3b14da6bb31451a3c9404b1d3211ce9912baf6318364ff679a218bfb"
)

FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_README = B3_DIR / "README.md"
B2_BOARD = (
    HARDWARE
    / "mf1750_devkitc_b2_pcba_margin"
    / "mf1750_devkitc_b2_pcba_margin.kicad_pcb"
)
BOARD_VERIFIER = HARDWARE / "verify_mf1750_wroom_b3_board_r3.py"
R7_HELPER = HARDWARE / "build_mf1750_wroom_b3_r7_drc_hygiene.py"

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8_epd_edge_access.kicad_pcb"
OUTPUT_REPORT = STAGING / "r8_epd_edge_access_report.json"
OUTPUT_DRC = STAGING / "r8_epd_edge_access_drc.json"
PREVIEW_DIR = STAGING / "r8_epd_edge_access_preview"
OUTPUT_TOP = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8_epd_edge_access_top.png"
OUTPUT_BOTTOM = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8_epd_edge_access_bottom.png"

EXPECTED_SOURCE_COPPER = 1217
EXPECTED_CANDIDATE_COPPER = 1217
EXPECTED_EPD_ADDED_COPPER = 102
EXPECTED_EPD_TRACKS = 74
EXPECTED_EPD_VIAS = 28
EXPECTED_SOURCE_UNCONNECTED = 128
EXPECTED_CANDIDATE_UNCONNECTED = 126
EPD_NETS = frozenset(
    {
        "/EPD_BUF_CONNECT",
        "/EPD_FAULT_N",
        "/EPD_PWR_EN",
        "/MCU_BUSY_N",
        "/MCU_CS2",
        "/MCU_CSB",
        "/MCU_DC",
        "/MCU_RST_N",
        "/MCU_SCL",
        "/MCU_SI0",
    }
)

PROTECTED_HASHES = {
    SOURCE_BOARD: SOURCE_BOARD_SHA256,
    R7_HYGIENE_BOARD: R7_HYGIENE_SHA256,
    EDGE_ENGINE: EDGE_ENGINE_SHA256,
    FORMAL_PROJECT: (
        "2fa48d53bc7875764500644c2d75c642fbe58eebc81b84eea6276bf937a9fe6c"
    ),
    FORMAL_SCHEMATIC: (
        "158e54c1b8e0301860239bd69d837215caf2a9f5d5a34687a32fee922b310bf0"
    ),
    FORMAL_BOARD: (
        "6da0e247e50ba4ce9ea984d6f0da72d98c1ac31544bf1aecbbb449bf3707e3a7"
    ),
    FORMAL_README: (
        "94d55cda894ce2d9845b990559063280c19174d46cd44c5c40da4b44d1352af4"
    ),
    B2_BOARD: (
        "462e127279bacc894eab5e8cc242cd6d26e1d3ee87708ad398f8064b5a5c4238"
    ),
    BOARD_VERIFIER: (
        "ebd591073b2d93e9a289e431312d9ba17f1dd96bafbd6bcd40b8c42341b72745"
    ),
    R7_HELPER: (
        "a7cedba80c44cb52e4b18e62eeff2a3eab258c170b2708de2903b7dcfbe19b3a"
    ),
}


class RebaseError(edge.ProbeError):
    """Fail-closed R8 EPD + edge-access rebase error."""


def configure_edge_engine() -> None:
    """Bind the proven mutation engine to this frozen source and outputs."""
    edge.SOURCE_BOARD = SOURCE_BOARD
    edge.SOURCE_BOARD_SHA256 = SOURCE_BOARD_SHA256
    edge.OUTPUT_BOARD = OUTPUT_BOARD
    edge.OUTPUT_REPORT = OUTPUT_REPORT
    edge.OUTPUT_DRC = OUTPUT_DRC
    edge.PREVIEW_DIR = PREVIEW_DIR
    edge.OUTPUT_TOP = OUTPUT_TOP
    edge.OUTPUT_BOTTOM = OUTPUT_BOTTOM
    edge.PROTECTED_HASHES = PROTECTED_HASHES
    edge.EXPECTED_SOURCE_UNCONNECTED = EXPECTED_SOURCE_UNCONNECTED
    edge.EXPECTED_CANDIDATE_UNCONNECTED = EXPECTED_CANDIDATE_UNCONNECTED
    edge.ROUTING_UUID_SEED = 0xB3EA7801


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def signature_digest(values: Mapping[str, Any]) -> str:
    payload = json.dumps(
        sorted((uuid, signature) for uuid, signature in values.items()),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def copper_items(board: Any) -> dict[str, Any]:
    return {edge.item_uuid(item): item for item in board.GetTracks()}


def epd_route_preservation(candidate_path: Path) -> dict[str, Any]:
    hygiene = pcbnew.LoadBoard(str(R7_HYGIENE_BOARD.resolve()))
    source = pcbnew.LoadBoard(str(SOURCE_BOARD.resolve()))
    candidate = pcbnew.LoadBoard(str(candidate_path.resolve()))
    if any(board is None for board in (hygiene, source, candidate)):
        raise RebaseError("could not load boards for EPD-route preservation audit")

    hygiene_state = edge.board_state(hygiene)["tracks"]
    source_state = edge.board_state(source)["tracks"]
    candidate_state = edge.board_state(candidate)["tracks"]
    hygiene_ids = set(hygiene_state)
    source_ids = set(source_state)
    candidate_ids = set(candidate_state)
    epd_ids = source_ids - hygiene_ids
    source_non_vbus = source_ids - set(edge.SOURCE_USB_VBUS_TRACK_UUIDS)
    replacement_ids = candidate_ids - source_non_vbus

    source_objects = copper_items(source)
    epd_objects = {uuid: source_objects[uuid] for uuid in epd_ids}
    by_net: dict[str, collections.Counter[str]] = {}
    for item in epd_objects.values():
        kind = "via" if isinstance(item, pcbnew.PCB_VIA) else "track"
        by_net.setdefault(item.GetNetname(), collections.Counter())[kind] += 1

    tracks = sum(
        not isinstance(item, pcbnew.PCB_VIA) for item in epd_objects.values()
    )
    vias = sum(isinstance(item, pcbnew.PCB_VIA) for item in epd_objects.values())
    hygiene_drift = sorted(
        uuid
        for uuid in hygiene_ids & source_ids
        if hygiene_state[uuid] != source_state[uuid]
    )
    epd_missing_or_changed = sorted(
        uuid
        for uuid in epd_ids
        if uuid not in candidate_state or candidate_state[uuid] != source_state[uuid]
    )
    candidate_retained_drift = sorted(
        uuid
        for uuid in source_non_vbus & candidate_ids
        if source_state[uuid] != candidate_state[uuid]
    )
    checks = {
        "hygiene_copper_count_1115": len(hygiene_ids) == 1115,
        "source_copper_count_1217": len(source_ids) == EXPECTED_SOURCE_COPPER,
        "candidate_copper_count_1217": len(candidate_ids)
        == EXPECTED_CANDIDATE_COPPER,
        "hygiene_is_exact_subset_of_epd_source": hygiene_ids <= source_ids
        and not hygiene_drift,
        "epd_added_copper_count_102": len(epd_ids) == EXPECTED_EPD_ADDED_COPPER,
        "epd_added_track_count_74": tracks == EXPECTED_EPD_TRACKS,
        "epd_added_via_count_28": vias == EXPECTED_EPD_VIAS,
        "epd_net_set_exact": {item.GetNetname() for item in epd_objects.values()}
        == EPD_NETS,
        "all_102_epd_objects_preserved_by_uuid_and_geometry": not epd_missing_or_changed,
        "all_other_source_copper_preserved_by_uuid_and_geometry": source_non_vbus
        <= candidate_ids
        and not candidate_retained_drift,
        "only_exact_eight_source_vbus_objects_removed": not (
            set(edge.SOURCE_USB_VBUS_TRACK_UUIDS) & candidate_ids
        ),
        "exactly_eight_replacement_vbus_objects_added": len(replacement_ids) == 8,
    }
    if not all(checks.values()):
        raise RebaseError(
            "EPD-route preservation audit failed: "
            + json.dumps(checks, ensure_ascii=False, sort_keys=True)
        )
    return {
        "passed": True,
        "checks": checks,
        "hygiene_copper_count": len(hygiene_ids),
        "source_copper_count": len(source_ids),
        "candidate_copper_count": len(candidate_ids),
        "epd_added_copper_count": len(epd_ids),
        "epd_added_track_count": tracks,
        "epd_added_via_count": vias,
        "epd_added_uuid_signature_sha256": signature_digest(
            {uuid: source_state[uuid] for uuid in epd_ids}
        ),
        "epd_added_by_net": {
            net: dict(sorted(counts.items())) for net, counts in sorted(by_net.items())
        },
        "epd_missing_or_changed": epd_missing_or_changed,
        "other_retained_copper_drift": candidate_retained_drift,
        "replacement_vbus_uuids": sorted(replacement_ids),
    }


def validate_r8_drc(
    source: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    result = edge.validate_drc(source, candidate)
    checks = result["checks"]
    checks["source_unconnected_128"] = checks.pop("source_unconnected_141")
    checks["candidate_unconnected_126"] = checks.pop("candidate_unconnected_139")
    if not all(checks.values()):
        raise RebaseError("renamed R8 DRC gate is not fully true")
    return result


def artifact_record(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="run every gate without publishing staging artifacts",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    configure_edge_engine()
    script = Path(__file__).resolve()
    script_hash_before = sha256_file(script)
    try:
        if pcbnew is None:
            raise RebaseError(f"KiCad pcbnew unavailable: {edge.PCBNEW_IMPORT_ERROR}")
        if str(pcbnew.GetBuildVersion()).split(".", 1)[0] != "10":
            raise RebaseError(f"KiCad 10 required, found {pcbnew.GetBuildVersion()}")
        edge.assert_output_scope()
        edge.assert_no_locks()
        protected_before = edge.protected_hashes()

        with tempfile.TemporaryDirectory(prefix="mf1750-r8-epd-edge-") as name:
            temp_dir = Path(name)
            first = temp_dir / "run1.kicad_pcb"
            second = temp_dir / "run2.kicad_pcb"
            first_result = edge.build_once(first)
            second_result = edge.build_once(second)
            first_bytes = first.read_bytes()
            second_bytes = second.read_bytes()
            deterministic = {
                "passed": first_bytes == second_bytes,
                "run1_sha256": hashlib.sha256(first_bytes).hexdigest(),
                "run2_sha256": hashlib.sha256(second_bytes).hexdigest(),
                "run1_bytes": len(first_bytes),
                "run2_bytes": len(second_bytes),
            }
            if not deterministic["passed"]:
                raise RebaseError("double build is not byte deterministic")
            if first_result["changes"] != second_result["changes"]:
                raise RebaseError("double-build change evidence differs")
            if first_result["audit"] != second_result["audit"]:
                raise RebaseError("double-build preservation evidence differs")

            epd_preservation = epd_route_preservation(first)
            source_drc = edge.r7base.run_drc(
                SOURCE_BOARD, "mf1750-r8-epd-edge-source-drc-"
            )
            candidate_drc = edge.r7base.run_drc(
                first, "mf1750-r8-epd-edge-candidate-drc-"
            )
            drc_gate = validate_r8_drc(source_drc, candidate_drc)
            source_vbus = edge.vbus_connectivity_evidence(SOURCE_BOARD)
            candidate_vbus = edge.vbus_connectivity_evidence(first)
            mechanics = edge.mechanical_evidence(first)
            verifier = edge.r7base.run_board_verifier(first)
            top_bytes = edge.r7base.render(first, "top", OUTPUT_TOP, temp_dir)
            bottom_bytes = edge.r7base.render(
                first, "bottom", OUTPUT_BOTTOM, temp_dir
            )
            candidate_drc_bytes = json_bytes(candidate_drc["raw"])

            script_hash_after = sha256_file(script)
            if script_hash_after != script_hash_before:
                raise RebaseError("builder changed while running")
            protected_after = edge.protected_hashes()
            if protected_after != protected_before:
                raise RebaseError("protected input changed while building")
            edge.assert_no_locks()

            artifacts = {
                "board": artifact_record(OUTPUT_BOARD, first_bytes),
                "drc": artifact_record(OUTPUT_DRC, candidate_drc_bytes),
                "top": artifact_record(OUTPUT_TOP, top_bytes),
                "bottom": artifact_record(OUTPUT_BOTTOM, bottom_bytes),
            }
            report = {
                "schema": 1,
                "tool": script.name,
                "mode": "REVISION_TO_STAGING_ONLY",
                "state": "R8_EPD_EDGE_ACCESS_CANDIDATE_HOLD",
                "overall_status": "HOLD",
                "operation_completed": True,
                "locally_verified": False,
                "manufacturing_release": False,
                "hardware_accessed": False,
                "network_accessed": False,
                "serial_or_com_accessed": False,
                "formal_project_modified": False,
                "formal_schematic_modified": False,
                "formal_board_modified": False,
                "formal_readme_modified": False,
                "epd_source_modified": False,
                "generated_at_utc": dt.datetime.now(dt.timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "kicad": {
                    "pcbnew": str(pcbnew.GetBuildVersion()),
                    "cli": str(edge.KICAD_CLI.resolve()),
                    "python": str(edge.KICAD_PYTHON.resolve()),
                },
                "builder": {
                    "path": str(script),
                    "sha256_before": script_hash_before,
                    "sha256_after": script_hash_after,
                    "unchanged": True,
                    "edge_engine": {
                        "path": str(EDGE_ENGINE.resolve()),
                        "sha256": EDGE_ENGINE_SHA256,
                    },
                },
                "source": {
                    "path": str(SOURCE_BOARD.resolve()),
                    "sha256": SOURCE_BOARD_SHA256,
                    "bytes": SOURCE_BOARD.stat().st_size,
                    "fixed_input": True,
                    "copper_count": EXPECTED_SOURCE_COPPER,
                },
                "protected_hashes_before": protected_before,
                "protected_hashes_after": protected_after,
                "protected_hashes_unchanged": True,
                "changes": first_result["changes"],
                "preservation": first_result["audit"],
                "epd_route_preservation": epd_preservation,
                "determinism": deterministic,
                "drc": {
                    "source": {
                        key: value for key, value in source_drc.items() if key != "raw"
                    },
                    "candidate": {
                        key: value
                        for key, value in candidate_drc.items()
                        if key != "raw"
                    },
                    "gate": drc_gate,
                },
                "connectivity_evidence": {
                    "usb_vbus_source": source_vbus,
                    "usb_vbus_candidate": candidate_vbus,
                    "usb_vbus_conclusion": "CONNECTED_SET_PRESERVED_NOT_REDUCED",
                    "unconnected_reduction": {
                        "source_total": source_drc["unconnected_count"],
                        "candidate_total": candidate_drc["unconnected_count"],
                        "delta_by_net": drc_gate["unconnected_delta_by_net"],
                        "reason": "J5 A1/A12/B1/B12 solid-connect to the F.Cu GND plane; /USB_VBUS remains one connected set",
                        "all_other_net_ratline_counts_unchanged": True,
                    },
                },
                "project_board_verifier": verifier,
                "artifacts": artifacts,
                "mechanical_evidence": {
                    "board_outline_mm": [80.0, 125.0],
                    "switches": "centres retained; all side actuators rotated outward",
                    "j5": {
                        "position_mm": [3.65, 108.70],
                        "rotation_deg": 270.0,
                    },
                    "j6": mechanics,
                },
                "holds": [
                    "J6 connector choice, pack envelope, and /BAT_POS-GND-/BAT_NTC line-order authority remain HOLD",
                    "J5 enclosure cutout/cable envelope and SW1-SW5 pushrod travel remain HOLD",
                    "12 U1 0.20 mm thermal drills, the inherited /EPD_SW_3V3 dangling endpoint, and 126 remaining unconnected items remain HOLD",
                    "stackup/USB impedance, enclosure, assembly, thermal, RF, and manufacturing release remain HOLD",
                ],
                "check_only": bool(args.check_only),
            }
            preliminary_report = json_bytes(report)
            report["artifacts"]["report"] = {
                "path": str(OUTPUT_REPORT.resolve()),
                "bytes_without_self_record": len(preliminary_report),
                "self_hash_intentionally_omitted": True,
            }
            report_bytes = json_bytes(report)

            if not args.check_only:
                edge.r7base.atomic_write_bytes(OUTPUT_BOARD, first_bytes)
                edge.r7base.atomic_write_bytes(OUTPUT_DRC, candidate_drc_bytes)
                edge.r7base.atomic_write_bytes(OUTPUT_TOP, top_bytes)
                edge.r7base.atomic_write_bytes(OUTPUT_BOTTOM, bottom_bytes)
                edge.r7base.atomic_write_bytes(OUTPUT_REPORT, report_bytes)
                published = {
                    "board": sha256_file(OUTPUT_BOARD),
                    "drc": sha256_file(OUTPUT_DRC),
                    "top": sha256_file(OUTPUT_TOP),
                    "bottom": sha256_file(OUTPUT_BOTTOM),
                }
                expected = {
                    key: value["sha256"]
                    for key, value in artifacts.items()
                    if key != "report"
                }
                if published != expected:
                    raise RebaseError("published artifact hash differs")
                if edge.protected_hashes() != protected_before:
                    raise RebaseError("protected input changed during publication")

        summary = {
            "state": report["state"],
            "overall_status": report["overall_status"],
            "operation_completed": report["operation_completed"],
            "board": report["artifacts"]["board"],
            "drc": report["drc"]["candidate"],
            "deterministic": report["determinism"]["passed"],
            "preservation_passed": report["preservation"]["passed"],
            "epd_route_preservation_passed": report["epd_route_preservation"][
                "passed"
            ],
            "project_board_verifier": report["project_board_verifier"]["summary"],
            "check_only": bool(args.check_only),
        }
        sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        return 0
    except Exception as exc:
        failure = {
            "schema": 1,
            "tool": Path(__file__).name,
            "state": "R8_EPD_EDGE_ACCESS_BUILD_FAILED_HOLD",
            "overall_status": "HOLD",
            "operation_completed": False,
            "hardware_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "candidate_artifacts_published": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        if not args.check_only:
            failure["failure_report"] = str(OUTPUT_REPORT.resolve())
            edge.r7base.atomic_write_bytes(OUTPUT_REPORT, json_bytes(failure))
        sys.stdout.write(json.dumps(failure, ensure_ascii=False, indent=2) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
