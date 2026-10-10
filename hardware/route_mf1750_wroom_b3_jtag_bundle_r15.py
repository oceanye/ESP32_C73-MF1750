#!/usr/bin/env python3
"""Route only the four JTAG GPIO nets on the frozen R12 staging PCB.

Operating mode: REVISION.  The R12 source is SHA-bound and immutable.  This
builder adds deterministic 0.20 mm copper and 0.60/0.30 mm through-vias only
for GPIO39..42.  In1.Cu, B2, the WROOM antenna keepout, source copper,
footprints, zones, formal files, documentation, and the UUID registry are
protected.  Any unrelated ratline or inherited DRC fingerprint drift fails
closed.
"""

from __future__ import annotations

import collections
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

ENGINE = HARDWARE / "route_mf1750_wroom_b3_user_key_2_n_r12.py"
ENGINE_SHA256 = "b4bc903b872b997d2060a9fe681a3d76ca56774a7df43100a015ddcaae9875cf"
SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r12_r11_user_key_2_n_routed.kicad_pcb"
SOURCE_SHA256 = "3a92f2aa31292032f38fcbae7152e67d20ef1cf50e0e619f6243faf3abe32ea3"

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r15_r12_jtag_bundle_routed.kicad_pcb"
REPORT_JSON = STAGING / "r15_r12_jtag_bundle_route_report.json"
SOURCE_DRC_JSON = STAGING / "r15_r12_jtag_bundle_source_drc.json"
CANDIDATE_DRC_JSON = STAGING / "r15_r12_jtag_bundle_drc.json"
BOARD_VERIFIER_JSON = STAGING / "r15_r12_jtag_bundle_board_verifier.json"
PREVIEW_DIR = STAGING / "r15_r12_jtag_bundle_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r15_r12_jtag_bundle_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r15_r12_jtag_bundle_bottom.png"
ISO_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r15_r12_jtag_bundle_iso.png"
FRONT_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r15_r12_jtag_bundle_front.svg"
BACK_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r15_r12_jtag_bundle_back.svg"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
ROOT_README = ROOT / "README.md"
B3_README = B3_DIR / "README.md"
STATUS_HANDOFF = ROOT / "docs" / "STATUS_HANDOFF.md"
UUID_REGISTRY = B3_DIR / "ROUTING_UUID_SEEDS.json"

ROUTING_UUID_SEED = 1750931
ALLOWED_NETS = frozenset(
    {"/JTAG_GPIO39", "/JTAG_GPIO40", "/JTAG_GPIO41", "/JTAG_GPIO42"}
)
SIGNAL_WIDTH_MM = 0.20
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30
B2_BOTTOM_MM = 60.5
WROOM_ANTENNA_KEEPOUT = (58.75, 66.0, 79.75, 114.0)
EXPECTED_SOURCE_COPPER = 1321
EXPECTED_ADDED_TRACKS = 20
EXPECTED_ADDED_VIAS = 12
EXPECTED_CANDIDATE_COPPER = 1353
EXPECTED_SOURCE_DRC = 13
EXPECTED_CANDIDATE_DRC = 13
EXPECTED_SOURCE_OPEN = 112
EXPECTED_CANDIDATE_OPEN = 108

PAD_CONTRACT = (
    ("U1", "32", "/JTAG_GPIO39", 47.1000, 98.7500),
    ("TP30", "1", "/JTAG_GPIO39", 49.0000, 123.0000),
    ("U1", "33", "/JTAG_GPIO40", 48.3700, 98.7500),
    ("TP31", "1", "/JTAG_GPIO40", 53.0000, 123.0000),
    ("U1", "34", "/JTAG_GPIO41", 49.6400, 98.7500),
    ("TP32", "1", "/JTAG_GPIO41", 57.0000, 123.0000),
    ("U1", "35", "/JTAG_GPIO42", 50.9100, 98.7500),
    ("TP33", "1", "/JTAG_GPIO42", 61.0000, 123.0000),
)

# Short F.Cu pad escapes drop to B.Cu.  A second via below the inherited
# EPD_FAULT_N diagonal moves each trunk to In2.Cu.  The ordered fanout begins
# below y=116 mm, after the inherited In2 DCDC/MCU trunks and below the WROOM
# antenna keepout, then returns to F.Cu immediately beside each SMD test pad.
ROUTES: tuple[tuple[str, str, tuple[tuple[float, float], ...]], ...] = (
    ("/JTAG_GPIO39", "F.Cu", ((47.1000, 98.7500), (47.1000, 100.4000))),
    ("/JTAG_GPIO39", "B.Cu", ((47.1000, 100.4000), (47.1000, 105.5000))),
    ("/JTAG_GPIO39", "In2.Cu", ((47.1000, 105.5000), (47.1000, 116.0000), (48.2000, 121.5000))),
    ("/JTAG_GPIO39", "F.Cu", ((48.2000, 121.5000), (49.0000, 123.0000))),
    ("/JTAG_GPIO40", "F.Cu", ((48.3700, 98.7500), (48.3700, 100.4000))),
    ("/JTAG_GPIO40", "B.Cu", ((48.3700, 100.4000), (48.3700, 105.5000))),
    ("/JTAG_GPIO40", "In2.Cu", ((48.3700, 105.5000), (48.3700, 116.0000), (52.2000, 121.5000))),
    ("/JTAG_GPIO40", "F.Cu", ((52.2000, 121.5000), (53.0000, 123.0000))),
    ("/JTAG_GPIO41", "F.Cu", ((49.6400, 98.7500), (49.6400, 100.4000))),
    ("/JTAG_GPIO41", "B.Cu", ((49.6400, 100.4000), (49.6400, 105.5000))),
    ("/JTAG_GPIO41", "In2.Cu", ((49.6400, 105.5000), (49.6400, 116.0000), (56.2000, 121.5000))),
    ("/JTAG_GPIO41", "F.Cu", ((56.2000, 121.5000), (57.0000, 123.0000))),
    ("/JTAG_GPIO42", "F.Cu", ((50.9100, 98.7500), (50.9100, 100.4000))),
    ("/JTAG_GPIO42", "B.Cu", ((50.9100, 100.4000), (50.9100, 105.5000))),
    ("/JTAG_GPIO42", "In2.Cu", ((50.9100, 105.5000), (50.9100, 116.0000), (60.2000, 121.5000))),
    ("/JTAG_GPIO42", "F.Cu", ((60.2000, 121.5000), (61.0000, 123.0000))),
)

VIAS: tuple[tuple[str, float, float], ...] = (
    ("/JTAG_GPIO39", 47.1000, 100.4000),
    ("/JTAG_GPIO39", 47.1000, 105.5000),
    ("/JTAG_GPIO39", 48.2000, 121.5000),
    ("/JTAG_GPIO40", 48.3700, 100.4000),
    ("/JTAG_GPIO40", 48.3700, 105.5000),
    ("/JTAG_GPIO40", 52.2000, 121.5000),
    ("/JTAG_GPIO41", 49.6400, 100.4000),
    ("/JTAG_GPIO41", 49.6400, 105.5000),
    ("/JTAG_GPIO41", 56.2000, 121.5000),
    ("/JTAG_GPIO42", 50.9100, 100.4000),
    ("/JTAG_GPIO42", 50.9100, 105.5000),
    ("/JTAG_GPIO42", 60.2000, 121.5000),
)


class RouteError(RuntimeError):
    """Fail-closed JTAG bundle route error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_engine():
    if not ENGINE.is_file() or sha256_file(ENGINE) != ENGINE_SHA256:
        raise RouteError("routing engine missing or hash-mismatched")
    spec = importlib.util.spec_from_file_location("_mf1750_r15_jtag_engine", ENGINE)
    if spec is None or spec.loader is None:
        raise RouteError("could not import routing engine")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


engine = load_engine()
pcbnew = engine.pcbnew
base = engine.base


def point_in_rect(point, rect) -> bool:
    x_value, y_value = point
    x0, y0, x1, y1 = rect
    return x0 <= x_value <= x1 and y0 <= y_value <= y1


def segment_hits_rect(start, end, rect) -> bool:
    x0, y0, x1, y1 = rect
    xa, ya = start
    xb, yb = end
    dx, dy = xb - xa, yb - ya
    lo, hi = 0.0, 1.0
    for p_value, q_value in zip(
        (-dx, dx, -dy, dy),
        (xa - x0, x1 - xa, ya - y0, y1 - ya),
        strict=True,
    ):
        if abs(p_value) < 1e-12:
            if q_value < 0:
                return False
            continue
        ratio = q_value / p_value
        if p_value < 0:
            lo = max(lo, ratio)
        else:
            hi = min(hi, ratio)
        if lo > hi:
            return False
    return True


def validate_source(board, before) -> dict[str, object]:
    pads = []
    for reference, number, net, x_mm, y_mm in PAD_CONTRACT:
        footprint = board.FindFootprintByReference(reference)
        if footprint is None:
            raise RouteError(f"missing footprint {reference}")
        matches = [
            pad
            for pad in footprint.Pads()
            if pad.GetNumber() == number
            and base.point_mm(pad.GetPosition()) == (x_mm, y_mm)
        ]
        if len(matches) != 1 or matches[0].GetNetname() != net:
            raise RouteError(f"pad contract drift: {reference}.{number}@{(x_mm, y_mm)}")
        pads.append(
            {"reference": reference, "pad": number, "net": net, "position_mm": [x_mm, y_mm]}
        )
    source_counts = collections.Counter(signature[1] for signature in before["tracks"].values())
    checks = {
        "source_copper_count_1321": len(before["tracks"]) == EXPECTED_SOURCE_COPPER,
        "source_copper_uuid_unique": before["copper_uuid_audit"]["passed"] is True,
        "source_has_no_jtag_bundle_copper": all(source_counts.get(net, 0) == 0 for net in ALLOWED_NETS),
        "pad_contract_exact": len(pads) == len(PAD_CONTRACT),
    }
    if not all(checks.values()):
        raise RouteError("source contract failed: " + json.dumps(checks, sort_keys=True))
    return {"passed": True, "checks": checks, "pads": pads}


def add_routes(board) -> set[str]:
    pcbnew.KIID.SeedGenerator(ROUTING_UUID_SEED)
    added_ids: list[str] = []
    for net_name, layer, points in ROUTES:
        if net_name not in ALLOWED_NETS or layer == "In1.Cu":
            raise RouteError(f"forbidden route recipe: {net_name} on {layer}")
        for start, end in zip(points, points[1:], strict=False):
            item = base.add_track(board, net_name, layer, SIGNAL_WIDTH_MM, start, end)
            added_ids.append(base.item_uuid(item))
    for net_name, x_mm, y_mm in VIAS:
        if net_name not in ALLOWED_NETS:
            raise RouteError(f"forbidden via net {net_name}")
        item = base.add_via(board, net_name, x_mm, y_mm)
        added_ids.append(base.item_uuid(item))
    if len(set(added_ids)) != len(added_ids):
        raise RouteError("new deterministic copper UUID collision")
    return set(added_ids)


def preservation_and_envelope_audit(candidate, before, added_ids) -> dict[str, object]:
    after = base.source_state(candidate)
    source_ids = set(before["tracks"])
    candidate_ids = set(after["tracks"])
    extra_ids = candidate_ids - source_ids
    missing_source = sorted(source_ids - candidate_ids)
    changed_source = sorted(
        item_id for item_id in source_ids & candidate_ids
        if before["tracks"][item_id] != after["tracks"][item_id]
    )
    unexpected_extra = sorted(extra_ids - added_ids)
    missing_added = sorted(added_ids - extra_ids)
    objects = {base.item_uuid(item): item for item in candidate.GetTracks()}
    findings = {"bad_net": [], "bad_width": [], "bad_via": [], "b2": [], "antenna": [], "in1": []}
    for item_id in sorted(extra_ids):
        item = objects[item_id]
        if item.GetNetname() not in ALLOWED_NETS:
            findings["bad_net"].append(item_id)
        if isinstance(item, pcbnew.PCB_VIA):
            points = [base.point_mm(item.GetPosition())]
            if (
                round(pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)), 6),
                round(pcbnew.ToMM(item.GetDrillValue()), 6),
            ) != (VIA_DIAMETER_MM, VIA_DRILL_MM):
                findings["bad_via"].append(item_id)
            antenna_hit = point_in_rect(points[0], WROOM_ANTENNA_KEEPOUT)
        else:
            points = [base.point_mm(item.GetStart()), base.point_mm(item.GetEnd())]
            if round(pcbnew.ToMM(item.GetWidth()), 6) != SIGNAL_WIDTH_MM:
                findings["bad_width"].append(item_id)
            if item.GetLayer() == base.layer_id(candidate, "In1.Cu"):
                findings["in1"].append(item_id)
            antenna_hit = segment_hits_rect(points[0], points[1], WROOM_ANTENNA_KEEPOUT)
        if any(y_value < B2_BOTTOM_MM for _, y_value in points):
            findings["b2"].append(item_id)
        if antenna_hit:
            findings["antenna"].append(item_id)
    new_counts = collections.Counter(after["tracks"][item_id][1] for item_id in extra_ids)
    expected_new_counts = {net: 8 for net in sorted(ALLOWED_NETS)}
    added_track_count = sum(not isinstance(objects[item_id], pcbnew.PCB_VIA) for item_id in extra_ids)
    added_via_count = sum(isinstance(objects[item_id], pcbnew.PCB_VIA) for item_id in extra_ids)
    checks = {
        "all_source_copper_uuid_geometry_exact": not missing_source and not changed_source,
        "only_deterministic_added_ids": not unexpected_extra and not missing_added,
        "new_uuid_intersection_with_source_zero": not (added_ids & source_ids),
        "candidate_copper_uuid_unique": after["copper_uuid_audit"]["passed"] is True,
        "candidate_copper_count_1353": len(after["tracks"]) == EXPECTED_CANDIDATE_COPPER,
        "added_track_count_20": added_track_count == EXPECTED_ADDED_TRACKS,
        "added_via_count_12": added_via_count == EXPECTED_ADDED_VIAS,
        "new_copper_only_jtag_bundle": dict(sorted(new_counts.items())) == expected_new_counts,
        "footprints_exact": before["footprints"] == after["footprints"],
        "zones_exact": before["zones"] == after["zones"],
        "no_new_copper_in_b2": not findings["b2"],
        "no_new_copper_in_antenna_keepout": not findings["antenna"],
        "no_new_signal_track_on_in1": not findings["in1"],
        "all_new_tracks_0p20_mm": not findings["bad_width"],
        "all_new_vias_0p60_0p30_mm": not findings["bad_via"],
        "no_bad_new_net": not findings["bad_net"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "source_copper_count": len(before["tracks"]),
        "candidate_copper_count": len(after["tracks"]),
        "added_ids": sorted(extra_ids),
        "removed_ids": missing_source,
        "changed_source_ids": changed_source,
        "unexpected_extra": unexpected_extra,
        "missing_added": missing_added,
        "new_net_counts": dict(sorted(new_counts.items())),
        "envelope_findings": findings,
    }


def unconnected_by_net(raw) -> dict[str, int]:
    counts: collections.Counter[str] = collections.Counter()
    for entry in raw.get("unconnected_items", []):
        names = []
        for item in entry.get("items", []):
            names.extend(re.findall(r"\[([^\]]+)\]", str(item.get("description", ""))))
        unique = set(name for name in names if name)
        counts[next(iter(unique)) if len(unique) == 1 else "<MIXED_OR_EMPTY>"] += 1
    return dict(sorted(counts.items()))


def violation_identity(raw) -> list[tuple[str, tuple[str, ...]]]:
    return sorted(
        (
            str(violation.get("type", "")),
            tuple(sorted(str(item.get("uuid", "")) for item in violation.get("items", []))),
        )
        for violation in raw.get("violations", [])
    )


def drc_gate(source, candidate) -> dict[str, object]:
    source_nets = unconnected_by_net(source["raw"])
    candidate_nets = unconnected_by_net(candidate["raw"])
    other_nets = (set(source_nets) | set(candidate_nets)) - ALLOWED_NETS
    other_drift = {
        net: {"source": source_nets.get(net, 0), "candidate": candidate_nets.get(net, 0)}
        for net in sorted(other_nets)
        if source_nets.get(net, 0) != candidate_nets.get(net, 0)
    }
    checks = {
        "source_violation_count_13": source["violation_count"] == EXPECTED_SOURCE_DRC,
        "candidate_violation_count_13": candidate["violation_count"] == EXPECTED_CANDIDATE_DRC,
        "inherited_violation_identity_exact": violation_identity(source["raw"]) == violation_identity(candidate["raw"]),
        "source_open_112": source["unconnected_count"] == EXPECTED_SOURCE_OPEN,
        "candidate_open_108": candidate["unconnected_count"] == EXPECTED_CANDIDATE_OPEN,
        "exact_open_reduction_4": source["unconnected_count"] - candidate["unconnected_count"] == 4,
        "source_each_jtag_open_1": all(source_nets.get(net, 0) == 1 for net in ALLOWED_NETS),
        "candidate_each_jtag_open_0": all(candidate_nets.get(net, 0) == 0 for net in ALLOWED_NETS),
        "dcdc_en_remains_0": candidate_nets.get("/DCDC_EN", 0) == 0,
        "boot_n_remains_0": candidate_nets.get("/BOOT_N", 0) == 0,
        "ps_hold_remains_0": candidate_nets.get("/PS_HOLD", 0) == 0,
        "user_key_2_n_remains_0": candidate_nets.get("/USER_KEY_2_N", 0) == 0,
        "all_other_net_open_counts_unchanged": not other_drift,
        "schematic_parity_zero": candidate["schematic_parity_count"] == 0,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "source_unconnected_by_net": source_nets,
        "candidate_unconnected_by_net": candidate_nets,
        "other_net_drift": other_drift,
        "source_violation_identity": violation_identity(source["raw"]),
        "candidate_violation_identity": violation_identity(candidate["raw"]),
    }


def protected_hashes() -> dict[str, str | None]:
    paths = (
        SOURCE_BOARD, ENGINE, FORMAL_BOARD, FORMAL_SCHEMATIC, FORMAL_PROJECT,
        ROOT_README, B3_README, STATUS_HANDOFF, UUID_REGISTRY,
    )
    return {str(path.resolve()): sha256_file(path) if path.is_file() else None for path in paths}


def render_isometric(kicad_cli: Path) -> dict[str, object]:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mf1750-r15-jtag-iso-") as name:
        temporary = Path(name)
        outputs = [temporary / "iso1.png", temporary / "iso2.png"]
        hashes = []
        commands = []
        for output in outputs:
            command = [
                str(kicad_cli), "pcb", "render", "--side", "top", "--background", "opaque",
                "--quality", "high", "--width", "1800", "--height", "1600", "--perspective",
                "--floor", "--rotate", "315,0,45", "--output", str(output), str(OUTPUT_BOARD),
            ]
            completed = subprocess.run(
                command, cwd=ROOT, check=False, text=True, encoding="utf-8", errors="replace", capture_output=True
            )
            if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
                raise RouteError("isometric render failed: " + (completed.stderr.strip() or completed.stdout.strip()))
            hashes.append(sha256_file(output))
            commands.append(command)
        os.replace(outputs[0], ISO_PREVIEW)
    return {
        "path": str(ISO_PREVIEW),
        "bytes": ISO_PREVIEW.stat().st_size,
        "sha256": sha256_file(ISO_PREVIEW),
        "repeat_hashes": hashes,
        "byte_identical": hashes[0] == hashes[1],
        "classification": "VISUAL_EVIDENCE_ONLY_NOT_A_PCB_DETERMINISM_GATE",
        "commands": commands,
    }


def configure_engine() -> None:
    engine.SOURCE_BOARD = SOURCE_BOARD
    engine.SOURCE_SHA256 = SOURCE_SHA256
    engine.OUTPUT_BOARD = OUTPUT_BOARD
    engine.REPORT_JSON = REPORT_JSON
    engine.SOURCE_DRC_JSON = SOURCE_DRC_JSON
    engine.CANDIDATE_DRC_JSON = CANDIDATE_DRC_JSON
    engine.BOARD_VERIFIER_JSON = BOARD_VERIFIER_JSON
    engine.PREVIEW_DIR = PREVIEW_DIR
    engine.TOP_PREVIEW = TOP_PREVIEW
    engine.BOTTOM_PREVIEW = BOTTOM_PREVIEW
    engine.FRONT_COPPER_SVG = FRONT_COPPER_SVG
    engine.BACK_COPPER_SVG = BACK_COPPER_SVG
    engine.ROUTING_UUID_SEED = ROUTING_UUID_SEED
    engine.ALLOWED_NET = "/JTAG_BUNDLE_WRAPPER"
    engine.ALLOWED_NETS = ALLOWED_NETS
    engine.ROUTES = ROUTES
    engine.VIAS = VIAS
    engine.EXPECTED_SOURCE_COPPER = EXPECTED_SOURCE_COPPER
    engine.EXPECTED_CANDIDATE_COPPER = EXPECTED_CANDIDATE_COPPER
    engine.EXPECTED_ADDED_TRACKS = EXPECTED_ADDED_TRACKS
    engine.EXPECTED_ADDED_VIAS = EXPECTED_ADDED_VIAS
    engine.EXPECTED_SOURCE_DRC = EXPECTED_SOURCE_DRC
    engine.EXPECTED_CANDIDATE_DRC = EXPECTED_CANDIDATE_DRC
    engine.EXPECTED_SOURCE_OPEN = EXPECTED_SOURCE_OPEN
    engine.EXPECTED_CANDIDATE_OPEN = EXPECTED_CANDIDATE_OPEN
    engine.PAD_CONTRACT = PAD_CONTRACT
    engine.validate_source = validate_source
    engine.add_routes = add_routes
    engine.preservation_and_envelope_audit = preservation_and_envelope_audit
    engine.drc_gate = drc_gate
    engine.protected_hashes = protected_hashes


def rewrite_report(exit_code: int) -> None:
    if not REPORT_JSON.is_file():
        return
    report = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    passed = report.get("routing_checks_passed") is True and exit_code == 0
    report["operating_mode"] = "REVISION"
    report["mode"] = "STAGING_ONLY_JTAG_GPIO39_42_BUNDLE_ROUTE"
    report["revision"] = "R15_R12_JTAG_BUNDLE_STAGING"
    report["state"] = "R15_R12_JTAG_BUNDLE_ROUTED_CANDIDATE" if passed else "R15_R12_JTAG_BUNDLE_HOLD"
    report["overall_status"] = "ROUTING_SCOPE_VERIFIED_WHOLE_BOARD_HOLD" if passed else "HOLD"
    report["locally_verified"] = False
    report["source"] = {"role": "sole_editable_PCB_geometry_source", "path": str(SOURCE_BOARD), "sha256": SOURCE_SHA256}
    report["builder"] = {
        "path": str(Path(__file__).resolve()),
        "sha256": sha256_file(Path(__file__).resolve()),
        "routing_uuid_seed": ROUTING_UUID_SEED,
        "engine": {"path": str(ENGINE), "sha256": ENGINE_SHA256},
    }
    report["completed_scope"] = sorted(ALLOWED_NETS) if passed else []
    report["inherited_completed_scope"] = ["/DCDC_EN", "/BOOT_N", "/PS_HOLD", "/USER_KEY_2_N"] if passed else []
    if "output" in report:
        report["output"] = {"path": str(OUTPUT_BOARD), "bytes": OUTPUT_BOARD.stat().st_size, "sha256": sha256_file(OUTPUT_BOARD)}
    report["holds"] = [{"scope": "WHOLE_BOARD", "reason": "108 unrelated/held unconnected items remain; not manufacturing-ready"}]
    if passed:
        kicad_cli = base.find_kicad_cli()
        report.setdefault("artifacts", {})["isometric_preview"] = render_isometric(kicad_cli)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Iterable[str] | None = None) -> int:
    if not SOURCE_BOARD.is_file() or sha256_file(SOURCE_BOARD) != SOURCE_SHA256:
        raise RouteError("sole source PCB missing or SHA-256 mismatched")
    configure_engine()
    exit_code = engine.main(argv)
    rewrite_report(exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
