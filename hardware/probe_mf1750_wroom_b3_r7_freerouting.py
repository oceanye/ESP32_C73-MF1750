#!/usr/bin/env python3
"""Create and audit a staging-only R7 Freerouting probe for MF1750 B3.

This wrapper never runs or downloads Freerouting.  In export mode it derives a
locked probe seed and Specctra DSN from a closed, hash-pinned source allowlist.
The audited R7 DRC-hygiene board is the default; the R6 EPD-boundary source is
retained as an explicit alternate probe.  With ``--import-session`` it imports
an explicitly supplied SES into that profile's published seed, performs
fail-closed preservation, parity, DRC and connectivity checks in an OS
temporary directory, and only then publishes a *new* staging candidate.
Formal B3 files, both allowlisted sources and README are protected inputs.

Run with KiCad 10.0.3's bundled Python, not the system Python::

    & 'C:\Program Files\KiCad\10.0\bin\python.exe' `
      hardware\probe_mf1750_wroom_b3_r7_freerouting.py --dry-run

No manufacturing or fabrication readiness is claimed by a successful run.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    import pcbnew  # type: ignore[import-not-found]
except Exception as exc:  # pragma: no cover - exercised by wrong-host invocation
    pcbnew = None  # type: ignore[assignment]
    PCBNEW_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    PCBNEW_IMPORT_ERROR = ""


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"
STEM = "mf1750_wroom_b3_power_tf"

R6_SOURCE = STAGING / f"{STEM}_r6_epd_boundary_routed.kicad_pcb"
R6_SOURCE_SHA256 = (
    "41fcea36a5ca4cc117b77fa02fb4d6332b248863ad82b5fe25c65b0aa72bcf28"
)
R7_HYGIENE_SOURCE = STAGING / f"{STEM}_r7_drc_hygiene.kicad_pcb"
R7_HYGIENE_SOURCE_SHA256 = (
    "88dfc906bd8d15adccecc54ccdbb9a6d2e5f1ec3149ede199475923ba22c1cf8"
)
FORMAL_PROJECT = B3_DIR / f"{STEM}.kicad_pro"
FORMAL_SCHEMATIC = B3_DIR / f"{STEM}.kicad_sch"
FORMAL_BOARD = B3_DIR / f"{STEM}.kicad_pcb"
README = B3_DIR / "README.md"
B2_BOARD = (
    HARDWARE
    / "mf1750_devkitc_b2_pcba_margin"
    / "mf1750_devkitc_b2_pcba_margin.kicad_pcb"
)
BOARD_VERIFIER = HARDWARE / "verify_mf1750_wroom_b3_board_r3.py"

DEFAULT_KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
EXPECTED_KICAD_VERSION = "10.0.3"
EXPECTED_COUNTS = {
    "copper_layers": 4,
    "footprints": 180,
    "pads": 623,
    "tracks": 940,
    "vias": 175,
    "zones": 7,
}
EXPECTED_DSN = {
    "placements": 180,
    "wire_paths": 837,
    "route_vias": 175,
    "fixed_wiring_objects": 1012,
    "planes": 3,
    "keepouts": 44,
}
B2_PROTECTED_RECT_MM = {
    "x_min": 0.0,
    "x_max": 65.0,
    "y_max_exclusive": 60.5,
}
ANTENNA_KEEPOUT = {
    "footprint_reference": "U1",
    "zone_uuid": "43d903f0-2a56-4c35-afaa-3ef6694f2d0e",
    "bbox_mm": [58.75, 66.0, 21.0, 48.0],
    "layer_set_hex": "00000000_00000000_00000000_00000055",
}
R6_EXPECTED_BASELINE_DRC = {
    "violations": 36,
    "unconnected": 141,
    "schematic_parity": 0,
    "categories": {
        "drill_out_of_range": 12,
        "silk_edge_clearance": 22,
        "starved_thermal": 1,
        "track_dangling": 1,
    },
}
R7_HYGIENE_EXPECTED_BASELINE_DRC = {
    "violations": 13,
    "unconnected": 141,
    "schematic_parity": 0,
    "categories": {
        "drill_out_of_range": 12,
        "track_dangling": 1,
    },
}
FATAL_DRC_CATEGORIES = frozenset(
    {
        "clearance",
        "copper_edge_clearance",
        "copper_sliver",
        "courtyards_overlap",
        "hole_clearance",
        "hole_to_hole",
        "item_on_disabled_layer",
        "items_not_allowed",
        "shorting_items",
        "solder_mask_bridge",
        "track_not_centered_on_via",
        "tracks_crossing",
    }
)
PROJECT_SUPPORT_FILES = (
    "fp-lib-table",
    "sym-lib-table",
    "mf1750_local.kicad_sym",
    "b3_wroom_symbols.kicad_sym",
)
PROJECT_SUPPORT_DIRS = (
    "b3_wroom_footprints.pretty",
    "MF1750_Compact.pretty",
    "MF1750_Production.pretty",
)
PROTECTED_INPUTS = (
    R6_SOURCE,
    R7_HYGIENE_SOURCE,
    FORMAL_PROJECT,
    FORMAL_SCHEMATIC,
    FORMAL_BOARD,
    README,
)


@dataclass(frozen=True)
class SourceProfile:
    key: str
    source: Path
    sha256: str
    output_tag: str
    expected_drc: Mapping[str, object]


@dataclass(frozen=True)
class OutputPaths:
    seed_board: Path
    seed_dsn: Path
    seed_report: Path
    imported_board: Path
    import_report: Path


SOURCE_PROFILES = {
    "r7-hygiene": SourceProfile(
        key="r7-hygiene",
        source=R7_HYGIENE_SOURCE,
        sha256=R7_HYGIENE_SOURCE_SHA256,
        output_tag="r7_drc_hygiene",
        expected_drc=R7_HYGIENE_EXPECTED_BASELINE_DRC,
    ),
    "r6-epd": SourceProfile(
        key="r6-epd",
        source=R6_SOURCE,
        sha256=R6_SOURCE_SHA256,
        output_tag="r6_epd_boundary",
        expected_drc=R6_EXPECTED_BASELINE_DRC,
    ),
}
DEFAULT_SOURCE_PROFILE = "r7-hygiene"


def output_paths(profile: SourceProfile) -> OutputPaths:
    prefix = f"{STEM}_{profile.output_tag}_freerouting"
    return OutputPaths(
        seed_board=STAGING / f"{prefix}_probe_seed.kicad_pcb",
        seed_dsn=STAGING / f"{prefix}_probe_seed.dsn",
        seed_report=STAGING / f"{profile.output_tag}_freerouting_probe_seed_report.json",
        imported_board=STAGING / f"{prefix}_imported_candidate.kicad_pcb",
        import_report=STAGING / f"{profile.output_tag}_freerouting_import_report.json",
    )


class ProbeError(RuntimeError):
    """Fail-closed validation error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def natural_key(value: str) -> tuple[object, ...]:
    return tuple(
        int(token) if token.isdigit() else token.casefold()
        for token in re.split(r"(\d+)", value)
    )


def require_regular(path: Path, label: str, suffix: str | None = None) -> None:
    if path.is_symlink() or not path.is_file():
        raise ProbeError(f"{label} is absent or not a regular file: {path}")
    if suffix is not None and path.suffix.casefold() != suffix:
        raise ProbeError(f"{label} must end in {suffix}: {path}")
    if path.stat().st_size <= 0 or path.stat().st_size > 100 * 1024 * 1024:
        raise ProbeError(f"{label} has an unsafe size: {path.stat().st_size}")


def snapshot_bound_input(
    source: Path, destination: Path, label: str, suffix: str
) -> dict[str, object]:
    """Copy one immutable input and bind the exact bytes used downstream."""

    require_regular(source, label, suffix)
    before_size = source.stat().st_size
    before_hash = sha256_file(source)
    shutil.copyfile(source, destination)
    require_regular(destination, f"temporary {label}", suffix)
    snapshot_size = destination.stat().st_size
    snapshot_hash = sha256_file(destination)
    after_size = source.stat().st_size
    after_hash = sha256_file(source)
    if (
        before_size != snapshot_size
        or before_hash != snapshot_hash
        or after_size != snapshot_size
        or after_hash != snapshot_hash
    ):
        raise ProbeError(f"{label} changed while it was snapshotted")
    return {
        "path": str(source.resolve()),
        "bytes": snapshot_size,
        "sha256": snapshot_hash,
    }


def assert_bound_input_unchanged(
    source: Path, record: Mapping[str, object], label: str
) -> None:
    require_regular(source, label, source.suffix.casefold())
    if (
        record.get("path") != str(source.resolve())
        or record.get("bytes") != source.stat().st_size
        or record.get("sha256") != sha256_file(source)
    ):
        raise ProbeError(f"{label} changed after its immutable snapshot")


def protected_snapshot() -> dict[str, str]:
    records: dict[str, str] = {}
    for path in PROTECTED_INPUTS:
        require_regular(path, "protected input")
        records[str(path.resolve())] = sha256_file(path)
    for profile in SOURCE_PROFILES.values():
        actual = records[str(profile.source.resolve())]
        if actual != profile.sha256:
            raise ProbeError(
                f"allowlisted source {profile.key} SHA-256 differs: "
                f"{actual} != {profile.sha256}"
            )
    return records


def assert_protected_unchanged(expected: Mapping[str, str], stage: str) -> None:
    current = protected_snapshot()
    if current != dict(expected):
        raise ProbeError(f"protected source changed {stage}")


def find_locks() -> list[Path]:
    locks: set[Path] = set()
    for directory in (B3_DIR, STAGING, B2_BOARD.parent):
        if directory.is_dir():
            locks.update(path.resolve() for path in directory.glob("~*.lck"))
    return sorted(locks, key=lambda value: str(value).casefold())


def require_no_locks() -> None:
    locks = find_locks()
    if locks:
        raise ProbeError("close KiCad first: " + ", ".join(map(str, locks)))


def require_output_paths_absent(paths: Sequence[Path]) -> None:
    staging = STAGING.resolve()
    if STAGING.is_symlink() or not STAGING.is_dir():
        raise ProbeError(f"staging directory is absent or unsafe: {STAGING}")
    resolved: set[Path] = set()
    protected = {path.resolve() for path in PROTECTED_INPUTS}
    for path in paths:
        if path.parent.resolve() != staging:
            raise ProbeError(f"output is outside the fixed staging directory: {path}")
        if path.is_symlink() or path.exists():
            raise ProbeError(f"refusing to overwrite existing output: {path}")
        target = path.resolve(strict=False)
        if target in protected or target in resolved:
            raise ProbeError(f"output aliases a protected or duplicate path: {path}")
        resolved.add(target)


def resolve_kicad_cli(explicit: Path | None) -> tuple[Path, dict[str, object]]:
    if explicit is not None:
        candidates = [explicit]
    else:
        candidates = [DEFAULT_KICAD_CLI]
        located = shutil.which("kicad-cli")
        if located:
            candidates.append(Path(located))
    for candidate in candidates:
        if candidate is None:
            continue
        path = candidate.expanduser().resolve()
        if path.is_file() and not path.is_symlink():
            completed = subprocess.run(
                [str(path), "version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
            version = completed.stdout.strip()
            if completed.returncode == 0 and version == EXPECTED_KICAD_VERSION:
                return path, {
                    "path": str(path),
                    "version": version,
                    "sha256": sha256_file(path),
                }
    qualifier = "explicit " if explicit is not None else ""
    raise ProbeError(
        f"{qualifier}KiCad CLI {EXPECTED_KICAD_VERSION} was not found or differed"
    )


def require_pcbnew() -> str:
    if pcbnew is None:
        raise ProbeError(
            "KiCad pcbnew is unavailable; run with KiCad 10 bundled python.exe: "
            + PCBNEW_IMPORT_ERROR
        )
    version = str(pcbnew.GetBuildVersion())
    if version != EXPECTED_KICAD_VERSION:
        raise ProbeError(
            f"pcbnew {EXPECTED_KICAD_VERSION} is required; found {version!r}"
        )
    return version


def point(value: Any) -> tuple[int, int]:
    return int(value.x), int(value.y)


def item_uuid(value: Any) -> str:
    return str(value.m_Uuid.AsString()).casefold()


def zone_signature(zone: Any) -> tuple[object, ...]:
    return (
        item_uuid(zone),
        str(zone.GetNetname()),
        str(zone.GetLayerSet().FmtHex()),
        bool(zone.GetIsRuleArea()),
        int(zone.GetAssignedPriority()),
        str(zone.Outline().Format()).replace("\r\n", "\n"),
    )


def pad_signature(pad: Any) -> tuple[object, ...]:
    return (
        item_uuid(pad),
        str(pad.GetNumber()),
        str(pad.GetNetname()),
        point(pad.GetPosition()),
        point(pad.GetFPRelativePosition()),
        float(pad.GetOrientationDegrees()),
        point(pad.GetSize()),
        point(pad.GetDrillSize()),
        int(pad.GetShape()),
        int(pad.GetDrillShape()),
        int(pad.GetAttribute()),
        str(pad.GetLayerSet().FmtHex()),
    )


def footprint_signature(footprint: Any) -> tuple[object, ...]:
    return (
        item_uuid(footprint),
        str(footprint.GetReference()),
        str(footprint.GetValue()),
        str(footprint.GetFPID().GetUniStringLibId()),
        point(footprint.GetPosition()),
        float(footprint.GetOrientationDegrees()),
        int(footprint.GetLayer()),
        bool(footprint.IsFlipped()),
        tuple(sorted((pad_signature(pad) for pad in footprint.Pads()), key=repr)),
        tuple(sorted((zone_signature(zone) for zone in footprint.Zones()), key=repr)),
    )


def route_signature(item: Any) -> tuple[object, ...]:
    if isinstance(item, pcbnew.PCB_VIA):
        top = int(item.TopLayer())
        bottom = int(item.BottomLayer())
        return (
            "via",
            item_uuid(item),
            str(item.GetNetname()),
            point(item.GetPosition()),
            int(item.GetWidth(top)),
            int(item.GetWidth(bottom)),
            int(item.GetDrillValue()),
            top,
            bottom,
            int(item.GetViaType()),
        )
    if isinstance(item, pcbnew.PCB_ARC):
        return (
            "arc",
            item_uuid(item),
            str(item.GetNetname()),
            point(item.GetStart()),
            point(item.GetMid()),
            point(item.GetEnd()),
            int(item.GetLayer()),
            int(item.GetWidth()),
        )
    return (
        "segment",
        item_uuid(item),
        str(item.GetNetname()),
        point(item.GetStart()),
        point(item.GetEnd()),
        int(item.GetLayer()),
        int(item.GetWidth()),
    )


def geometry_snapshot(board: Any) -> dict[str, object]:
    footprints = list(board.GetFootprints())
    copper = list(board.GetTracks())
    tracks = [item for item in copper if not isinstance(item, pcbnew.PCB_VIA)]
    vias = [item for item in copper if isinstance(item, pcbnew.PCB_VIA)]
    zones = list(board.Zones())
    return {
        "copper_layers": int(board.GetCopperLayerCount()),
        "footprints": {
            item_uuid(item): footprint_signature(item) for item in footprints
        },
        "routes": {item_uuid(item): route_signature(item) for item in copper},
        "zones": {item_uuid(item): zone_signature(item) for item in zones},
        "counts": {
            "copper_layers": int(board.GetCopperLayerCount()),
            "footprints": len(footprints),
            "pads": sum(len(list(item.Pads())) for item in footprints),
            "tracks": len(tracks),
            "vias": len(vias),
            "zones": len(zones),
        },
    }


def require_expected_source_geometry(snapshot: Mapping[str, object]) -> None:
    if snapshot.get("counts") != EXPECTED_COUNTS:
        raise ProbeError(
            "frozen R6 object counts changed: "
            + json.dumps(snapshot.get("counts"), sort_keys=True)
        )


def load_board(path: Path, label: str) -> Any:
    require_regular(path, label, ".kicad_pcb")
    board = pcbnew.LoadBoard(str(path))
    if board is None:
        raise ProbeError(f"pcbnew could not load {label}: {path}")
    return board


def lock_seed(board: Any) -> dict[str, int]:
    footprints = list(board.GetFootprints())
    copper = list(board.GetTracks())
    zones = list(board.Zones())
    for item in footprints:
        item.SetLocked(True)
    for item in copper:
        item.SetLocked(True)
    for item in zones:
        item.SetLocked(True)
    return {
        "footprints": len(footprints),
        "copper": len(copper),
        "zones": len(zones),
    }


def require_seed_locks(board: Any) -> dict[str, int]:
    footprints = list(board.GetFootprints())
    copper = list(board.GetTracks())
    zones = list(board.Zones())
    locked = {
        "footprints": sum(bool(item.IsLocked()) for item in footprints),
        "copper": sum(bool(item.IsLocked()) for item in copper),
        "zones": sum(bool(item.IsLocked()) for item in zones),
    }
    expected = {
        "footprints": len(footprints),
        "copper": len(copper),
        "zones": len(zones),
    }
    if locked != expected:
        raise ProbeError(f"seed lock coverage differs: {locked} != {expected}")
    return locked


def require_candidate_lock_preservation(seed: Any, candidate: Any) -> dict[str, int]:
    """Require every seed-owned object to remain locked after SES import.

    Freerouting is expected to add new tracks/vias, and KiCad may legitimately
    import those new objects as unlocked.  Lock coverage therefore follows the
    immutable seed UUID set instead of incorrectly requiring new routes to be
    locked too.
    """

    seed_footprints = {item_uuid(item) for item in seed.GetFootprints()}
    seed_routes = {item_uuid(item) for item in seed.GetTracks()}
    seed_zones = {item_uuid(item) for item in seed.Zones()}
    candidate_footprints = {
        item_uuid(item): item for item in candidate.GetFootprints()
    }
    candidate_routes = {item_uuid(item): item for item in candidate.GetTracks()}
    candidate_zones = {item_uuid(item): item for item in candidate.Zones()}

    missing = {
        "footprints": sorted(seed_footprints - set(candidate_footprints)),
        "routes": sorted(seed_routes - set(candidate_routes)),
        "zones": sorted(seed_zones - set(candidate_zones)),
    }
    unlocked = {
        "footprints": sorted(
            uuid
            for uuid in seed_footprints
            if uuid in candidate_footprints
            and not bool(candidate_footprints[uuid].IsLocked())
        ),
        "routes": sorted(
            uuid
            for uuid in seed_routes
            if uuid in candidate_routes and not bool(candidate_routes[uuid].IsLocked())
        ),
        "zones": sorted(
            uuid
            for uuid in seed_zones
            if uuid in candidate_zones and not bool(candidate_zones[uuid].IsLocked())
        ),
    }
    if any(missing.values()) or any(unlocked.values()):
        raise ProbeError(
            "seed lock preservation differs after SES import: "
            + json.dumps(
                {
                    "missing": {key: value[:10] for key, value in missing.items()},
                    "unlocked": {key: value[:10] for key, value in unlocked.items()},
                },
                sort_keys=True,
            )
        )
    return {
        "seed_footprints_locked": len(seed_footprints),
        "seed_routes_locked": len(seed_routes),
        "seed_zones_locked": len(seed_zones),
        "new_routes": len(set(candidate_routes) - seed_routes),
    }


def _bbox_mm(item: Any) -> tuple[float, float, float, float]:
    box = item.GetBoundingBox()
    x0 = float(pcbnew.ToMM(box.GetX()))
    y0 = float(pcbnew.ToMM(box.GetY()))
    return (
        x0,
        y0,
        x0 + float(pcbnew.ToMM(box.GetWidth())),
        y0 + float(pcbnew.ToMM(box.GetHeight())),
    )


def require_antenna_keepout(board: Any) -> dict[str, object]:
    matches: list[tuple[Any, Any]] = []
    for footprint in board.GetFootprints():
        for zone in footprint.Zones():
            if item_uuid(zone) == ANTENNA_KEEPOUT["zone_uuid"]:
                matches.append((footprint, zone))
    if len(matches) != 1:
        raise ProbeError("frozen U1 antenna keepout identity differs")
    footprint, zone = matches[0]
    box = zone.GetBoundingBox()
    bbox = [
        float(pcbnew.ToMM(box.GetX())),
        float(pcbnew.ToMM(box.GetY())),
        float(pcbnew.ToMM(box.GetWidth())),
        float(pcbnew.ToMM(box.GetHeight())),
    ]
    if (
        footprint.GetReference() != ANTENNA_KEEPOUT["footprint_reference"]
        or not bool(zone.GetIsRuleArea())
        or not bool(zone.GetDoNotAllowTracks())
        or not bool(zone.GetDoNotAllowVias())
        or str(zone.GetLayerSet().FmtHex()) != ANTENNA_KEEPOUT["layer_set_hex"]
        or any(
            abs(actual - expected) > 1e-6
            for actual, expected in zip(bbox, ANTENNA_KEEPOUT["bbox_mm"])
        )
    ):
        raise ProbeError("frozen U1 antenna keepout geometry or rules differ")
    return {
        "footprint_reference": footprint.GetReference(),
        "zone_uuid": item_uuid(zone),
        "bbox_mm": bbox,
        "layer_set_hex": str(zone.GetLayerSet().FmtHex()),
        "tracks_not_allowed": True,
        "vias_not_allowed": True,
    }


def audit_new_copper_regions(seed: Any, candidate: Any) -> dict[str, object]:
    """Reject new autorouter copper in the frozen B2 or antenna keepout areas."""

    seed_antenna = require_antenna_keepout(seed)
    candidate_antenna = require_antenna_keepout(candidate)
    if seed_antenna != candidate_antenna:
        raise ProbeError("candidate antenna keepout differs from seed")
    seed_route_uuids = {item_uuid(item) for item in seed.GetTracks()}
    new_routes = [
        item for item in candidate.GetTracks() if item_uuid(item) not in seed_route_uuids
    ]
    antenna_x0, antenna_y0, antenna_width, antenna_height = ANTENNA_KEEPOUT[
        "bbox_mm"
    ]
    antenna_x1 = antenna_x0 + antenna_width
    antenna_y1 = antenna_y0 + antenna_height
    b2_hits: list[dict[str, object]] = []
    antenna_hits: list[dict[str, object]] = []
    for item in new_routes:
        x0, y0, x1, y1 = _bbox_mm(item)
        record = {
            "uuid": item_uuid(item),
            "kind": route_signature(item)[0],
            "net": str(item.GetNetname()),
            "bbox_mm": [x0, y0, x1, y1],
        }
        if (
            x1 >= B2_PROTECTED_RECT_MM["x_min"]
            and x0 <= B2_PROTECTED_RECT_MM["x_max"]
            and y0 < B2_PROTECTED_RECT_MM["y_max_exclusive"]
        ):
            b2_hits.append(record)
        if x1 >= antenna_x0 and x0 <= antenna_x1 and y1 >= antenna_y0 and y0 <= antenna_y1:
            antenna_hits.append(record)
    audit = {
        "new_copper_count": len(new_routes),
        "b2_protected_rect_mm": dict(B2_PROTECTED_RECT_MM),
        "b2_new_copper_hit_count": len(b2_hits),
        "b2_new_copper_hits": b2_hits[:50],
        "antenna_keepout": seed_antenna,
        "antenna_new_copper_hit_count": len(antenna_hits),
        "antenna_new_copper_hits": antenna_hits[:50],
    }
    if b2_hits or antenna_hits:
        raise ProbeError(
            "new autorouter copper entered a protected region: "
            + json.dumps(audit, sort_keys=True)
        )
    audit["passed"] = True
    return audit


def _extract_form(text: str, start: int) -> str:
    if start < 0 or start >= len(text) or text[start] != "(":
        raise ProbeError("S-expression form start is invalid")
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
            if depth < 0:
                break
    raise ProbeError("unbalanced S-expression form")


def direct_board_forms(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8", errors="strict")
    root = text.find("(kicad_pcb")
    if root < 0:
        raise ProbeError(f"KiCad PCB root is absent: {path}")
    root_form = _extract_form(text, root)
    records: list[tuple[str, str]] = []
    depth = 0
    quoted = False
    escaped = False
    child_start: int | None = None
    for index, char in enumerate(root_form):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "(":
            if depth == 1:
                child_start = index
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 1 and child_start is not None:
                form = root_form[child_start : index + 1]
                match = re.match(r"\(\s*([^\s()]+)", form)
                if match is None:
                    raise ProbeError("could not identify direct PCB form")
                records.append((match.group(1), form))
                child_start = None
    return records


def exact_nonrouting_digest(path: Path) -> list[tuple[str, str]]:
    return [
        (head, hashlib.sha256(form.encode("utf-8")).hexdigest())
        for head, form in direct_board_forms(path)
        if head not in {"segment", "arc", "via"}
    ]


def exact_route_forms(path: Path) -> dict[str, tuple[str, str]]:
    records: dict[str, tuple[str, str]] = {}
    for head, form in direct_board_forms(path):
        if head not in {"segment", "arc", "via"}:
            continue
        match = re.search(r"\(uuid\s+([0-9a-fA-F-]{36})\)", form)
        if match is None:
            raise ProbeError(f"routing form lacks UUID in {path}")
        uuid = match.group(1).casefold()
        if uuid in records:
            raise ProbeError(f"duplicate routing UUID {uuid} in {path}")
        records[uuid] = (head, hashlib.sha256(form.encode("utf-8")).hexdigest())
    return records


def audit_import_preservation(seed: Path, candidate: Path) -> dict[str, object]:
    seed_nonrouting = exact_nonrouting_digest(seed)
    candidate_nonrouting = exact_nonrouting_digest(candidate)
    if seed_nonrouting != candidate_nonrouting:
        raise ProbeError("footprint/pad/zone/board non-routing forms changed on SES import")
    seed_routes = exact_route_forms(seed)
    candidate_routes = exact_route_forms(candidate)
    missing = sorted(set(seed_routes) - set(candidate_routes))
    changed = sorted(
        uuid
        for uuid in set(seed_routes) & set(candidate_routes)
        if seed_routes[uuid] != candidate_routes[uuid]
    )
    if missing or changed:
        raise ProbeError(
            "pre-existing copper changed on SES import: "
            + json.dumps({"missing": missing[:10], "changed": changed[:10]})
        )
    new_routes = sorted(set(candidate_routes) - set(seed_routes))
    return {
        "nonrouting_form_count": len(seed_nonrouting),
        "existing_route_count": len(seed_routes),
        "existing_routes_missing": 0,
        "existing_routes_changed": 0,
        "new_route_count": len(new_routes),
        "new_route_uuid_sample": new_routes[:20],
        "passed": True,
    }


def _dsn_section(text: str, name: str) -> str:
    match = re.search(rf"(?m)^\s*\({re.escape(name)}\b", text)
    if match is None:
        raise ProbeError(f"DSN section {name!r} is absent")
    return _extract_form(text, match.start() + len(match.group(0)) - len(match.group(0).lstrip()))


def _direct_child_forms(parent: str) -> list[tuple[str, str]]:
    """Return complete direct child forms, including multiline DSN wiring."""

    records: list[tuple[str, str]] = []
    depth = 0
    quoted = False
    escaped = False
    child_start: int | None = None
    for index, char in enumerate(parent):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "(":
            if depth == 1:
                child_start = index
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 1 and child_start is not None:
                form = parent[child_start : index + 1]
                match = re.match(r"\(\s*([^\s()]+)", form)
                if match is None:
                    raise ProbeError("could not identify direct child form")
                records.append((match.group(1), form))
                child_start = None
            if depth < 0:
                raise ProbeError("unbalanced direct child form")
    if depth != 0 or quoted:
        raise ProbeError("unbalanced parent S-expression")
    return records


def audit_dsn(path: Path) -> dict[str, object]:
    require_regular(path, "Specctra DSN", ".dsn")
    text = path.read_text(encoding="utf-8", errors="strict")
    if f'(host_version "{EXPECTED_KICAD_VERSION}")' not in text:
        raise ProbeError("DSN host version differs")
    wiring = _dsn_section(text, "wiring")
    wiring_forms = _direct_child_forms(wiring)
    unexpected_wiring_heads = sorted(
        {head for head, _ in wiring_forms if head not in {"wire", "via"}}
    )
    if unexpected_wiring_heads:
        raise ProbeError(
            "DSN wiring contains unexpected direct forms: "
            + repr(unexpected_wiring_heads)
        )
    wire_forms = [form for head, form in wiring_forms if head == "wire"]
    via_forms = [form for head, form in wiring_forms if head == "via"]
    objects = wire_forms + via_forms
    nonfixed = [
        form
        for form in objects
        if len(re.findall(r"\(type\s+fix\)", form)) != 1
        or len(re.findall(r"\(type\s+[^)]+\)", form)) != 1
    ]
    audit = {
        "placements": len(re.findall(r"(?m)^\s*\(place\b", text)),
        "wire_paths": len(wire_forms),
        "route_vias": len(via_forms),
        "fixed_wiring_objects": sum("(type fix)" in form for form in objects),
        "nonfixed_wiring_objects": len(nonfixed),
        "planes": len(re.findall(r"(?m)^\s*\(plane\b", text)),
        "keepouts": len(re.findall(r"(?m)^\s*\(keepout\b", text)),
        "layers": {
            name: len(re.findall(rf"(?m)^\s*\(layer\s+{re.escape(name)}\s*$", text))
            for name in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
        },
        "footprint_lock_token_count": len(re.findall(r"\(lock_type\b", text)),
        "source_lock_semantics": (
            "all exported wiring objects must be Specctra '(type fix)'; "
            "footprint locks remain authoritative in the seed PCB and are "
            "rechecked after SES import"
        ),
    }
    comparable = {key: audit[key] for key in EXPECTED_DSN}
    if comparable != EXPECTED_DSN:
        raise ProbeError(
            "DSN frozen structure differs: "
            + json.dumps(
                {
                    "actual": comparable,
                    "expected": EXPECTED_DSN,
                    "nonfixed_sample": nonfixed[:5],
                }
            )
        )
    if audit["nonfixed_wiring_objects"] != 0:
        raise ProbeError("DSN contains non-fixed pre-existing wiring")
    if audit["layers"] != {name: 1 for name in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")}:
        raise ProbeError("DSN four-layer structure differs")
    if "(type route)" in wiring or "(type protect)" in wiring:
        raise ProbeError("DSN wiring uses an unexpected route/protect type")
    audit["passed"] = True
    return audit


def prepare_self_contained(directory: Path, board: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=False)
    shutil.copy2(FORMAL_PROJECT, directory / f"{STEM}.kicad_pro")
    shutil.copy2(FORMAL_SCHEMATIC, directory / f"{STEM}.kicad_sch")
    shutil.copy2(board, directory / f"{STEM}.kicad_pcb")
    for name in PROJECT_SUPPORT_FILES:
        source = B3_DIR / name
        require_regular(source, f"project support file {name}")
        shutil.copy2(source, directory / name)
    for name in PROJECT_SUPPORT_DIRS:
        source = B3_DIR / name
        if source.is_symlink() or not source.is_dir():
            raise ProbeError(f"project support directory is absent or unsafe: {source}")
        shutil.copytree(source, directory / name)
    return directory / f"{STEM}.kicad_pcb"


def drc_audit(kicad_cli: Path, board: Path, directory: Path) -> dict[str, object]:
    source_hash_before = sha256_file(board)
    context_board = prepare_self_contained(directory, board)
    board_hash_before = sha256_file(context_board)
    output = directory / "drc.json"
    command = [
        str(kicad_cli),
        "pcb",
        "drc",
        "--format",
        "json",
        "--severity-all",
        "--schematic-parity",
        "--refill-zones",
        "--output",
        str(output),
        str(context_board),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
        cwd=directory,
    )
    if completed.returncode != 0 or not output.is_file():
        raise ProbeError(
            "KiCad DRC failed: "
            + (completed.stderr.strip() or completed.stdout.strip() or "no diagnostic")
        )
    if sha256_file(context_board) != board_hash_before:
        raise ProbeError("KiCad DRC modified its temporary input without --save-board")
    if sha256_file(board) != source_hash_before:
        raise ProbeError("KiCad DRC modified the caller-owned board")
    report = json.loads(output.read_text(encoding="utf-8", errors="strict"))
    if not isinstance(report, dict):
        raise ProbeError("KiCad DRC report is not an object")
    violations = report.get("violations")
    unconnected = report.get("unconnected_items")
    parity = report.get("schematic_parity")
    if not all(isinstance(value, list) for value in (violations, unconnected, parity)):
        raise ProbeError("KiCad DRC report arrays are incomplete")
    if report.get("kicad_version") != EXPECTED_KICAD_VERSION:
        raise ProbeError("KiCad DRC report version differs")
    if report.get("source") != context_board.name:
        raise ProbeError("KiCad DRC report source differs")
    malformed_violations = [
        index
        for index, item in enumerate(violations)
        if not isinstance(item, Mapping)
        or not isinstance(item.get("type"), str)
        or not str(item["type"]).strip()
    ]
    if malformed_violations:
        raise ProbeError(
            "KiCad DRC report contains malformed violations at indexes: "
            + repr(malformed_violations[:20])
        )
    categories = collections.Counter(
        str(item["type"]) for item in violations
    )
    return {
        "violations": len(violations),
        "unconnected": len(unconnected),
        "schematic_parity": len(parity),
        "categories": dict(sorted(categories.items())),
        "fatal_categories": {
            name: categories.get(name, 0) for name in sorted(FATAL_DRC_CATEGORIES)
        },
        "kicad_version": report.get("kicad_version"),
        "command": command,
        "report_sha256": sha256_file(output),
        "source_board_unchanged": True,
    }


def require_frozen_baseline_drc(
    value: Mapping[str, object], profile: SourceProfile
) -> None:
    actual = {
        "violations": value.get("violations"),
        "unconnected": value.get("unconnected"),
        "schematic_parity": value.get("schematic_parity"),
        "categories": value.get("categories"),
    }
    if actual != profile.expected_drc:
        raise ProbeError(
            f"{profile.key} baseline DRC identity differs: "
            + json.dumps({"actual": actual, "expected": profile.expected_drc})
        )


def require_candidate_drc_progress(
    baseline: Mapping[str, object], candidate: Mapping[str, object]
) -> dict[str, object]:
    if candidate.get("schematic_parity") != 0:
        raise ProbeError("imported candidate schematic parity is not zero")
    if not isinstance(candidate.get("violations"), int) or not isinstance(
        candidate.get("unconnected"), int
    ):
        raise ProbeError("candidate DRC counts are malformed")
    if int(candidate["unconnected"]) >= int(baseline["unconnected"]):
        raise ProbeError("SES did not reduce the unconnected-item count")
    if int(candidate["violations"]) > int(baseline["violations"]):
        raise ProbeError("SES increased the total DRC violation count")
    baseline_categories = collections.Counter(
        {str(key): int(value) for key, value in dict(baseline["categories"]).items()}
    )
    candidate_categories = collections.Counter(
        {str(key): int(value) for key, value in dict(candidate["categories"]).items()}
    )
    regressions = {
        key: candidate_categories[key] - baseline_categories[key]
        for key in candidate_categories
        if candidate_categories[key] > baseline_categories[key]
    }
    if regressions:
        raise ProbeError("SES introduced DRC-category regressions: " + repr(regressions))
    fatal = {
        key: candidate_categories[key]
        for key in FATAL_DRC_CATEGORIES
        if candidate_categories[key]
    }
    if fatal:
        raise ProbeError("SES candidate contains fatal DRC categories: " + repr(fatal))
    return {
        "unconnected_delta": int(candidate["unconnected"])
        - int(baseline["unconnected"]),
        "violation_delta": int(candidate["violations"])
        - int(baseline["violations"]),
        "category_regressions": {},
        "fatal_categories": {},
        "passed": True,
    }


def board_verifier(kicad_cli: Path, board: Path) -> dict[str, object]:
    command = [
        sys.executable,
        str(BOARD_VERIFIER),
        str(board),
        "--schematic",
        str(FORMAL_SCHEMATIC),
        "--b2",
        str(B2_BOARD),
        "--kicad-cli",
        str(kicad_cli),
        "--allow-board-only",
        "H3",
        "--allow-board-only",
        "H4",
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=ROOT,
    )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"board verifier did not return JSON: {exc}") from exc
    if (
        completed.returncode != 0
        or not isinstance(report, dict)
        or report.get("passed") is not True
        or report.get("summary") != {"total": 13, "passed": 13, "failed": 0}
        or report.get("boards_modified") is not False
        or report.get("schematics_modified") is not False
    ):
        raise ProbeError("project board verifier failed")
    return {
        "command": command,
        "passed": True,
        "summary": report["summary"],
        "input_sha256": sha256_file(board),
    }


def json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def publish_new_group(
    outputs: Sequence[tuple[Path, bytes]], protected: Mapping[str, str]
) -> None:
    require_output_paths_absent([path for path, _ in outputs])
    require_no_locks()
    assert_protected_unchanged(protected, "before staging publication")
    temporaries: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for destination, body in outputs:
            temporary = destination.with_name(
                f".{destination.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp"
            )
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                0o600,
            )
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(body)
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception:
                if temporary.exists():
                    temporary.unlink()
                raise
            temporaries.append((temporary, destination))
        for temporary, destination in temporaries:
            os.link(temporary, destination)
            published.append(destination)
        assert_protected_unchanged(protected, "after staging publication")
    except Exception as exc:
        rollback_errors: list[str] = []
        for path in reversed(published):
            try:
                if path.parent.resolve() == STAGING.resolve() and path.is_file():
                    path.unlink()
            except Exception as rollback_exc:  # preserve every rollback attempt
                rollback_errors.append(
                    f"{path}: {type(rollback_exc).__name__}: {rollback_exc}"
                )
        residual = [str(path) for path in published if path.exists()]
        if rollback_errors or residual:
            raise ProbeError(
                "staging publication failed and rollback was incomplete: "
                + json.dumps(
                    {
                        "original_error": f"{type(exc).__name__}: {exc}",
                        "rollback_errors": rollback_errors,
                        "residual_outputs": residual,
                    }
                )
            ) from exc
        raise
    finally:
        for temporary, _ in temporaries:
            try:
                if (
                    temporary.parent.resolve() == STAGING.resolve()
                    and temporary.exists()
                ):
                    temporary.unlink()
            except OSError:
                # Once every destination hardlink exists, temp-name cleanup must
                # not turn a successful, fully bound publication into false FAIL.
                pass


def seed_report(
    *,
    profile: SourceProfile,
    source: Path,
    seed: Path,
    dsn: Path,
    geometry: Mapping[str, object],
    lock_audit: Mapping[str, int],
    antenna_keepout: Mapping[str, object],
    dsn_audit: Mapping[str, object],
    drc: Mapping[str, object],
    verifier: Mapping[str, object],
    kicad_cli: Mapping[str, object],
    pcbnew_version: str,
    dry_run: bool,
) -> dict[str, object]:
    return {
        "schema": 1,
        "tool": Path(__file__).name,
        "tool_sha256": sha256_file(Path(__file__)),
        "generated_at_utc": utc_now(),
        "mode": "REVISION_TO_STAGING_ONLY",
        "state": "R7_FREEROUTING_PROBE_SEED_HOLD",
        "overall_status": "HOLD",
        "operation_completed": True,
        "locally_verified": False,
        "manufacturing_authorized": False,
        "dry_run": dry_run,
        "source_profile": profile.key,
        "source": file_record(source),
        "outputs": {
            "seed": file_record(seed),
            "dsn": file_record(dsn),
        },
        "geometry": geometry,
        "lock_audit": dict(lock_audit),
        "antenna_keepout": dict(antenna_keepout),
        "dsn_audit": dict(dsn_audit),
        "baseline_drc": dict(drc),
        "board_verifier": dict(verifier),
        "tools": {"pcbnew": pcbnew_version, "kicad_cli": dict(kicad_cli)},
        "freerouting_executed": False,
        "network_accessed": False,
        "hardware_accessed": False,
        "formal_board_modified": False,
        "r6_source_modified": False,
        "readme_modified": False,
        "holds": [
            "Freerouting has not been run by this wrapper",
            "R7 seed is an autorouting experiment, not a fabrication candidate",
            (
                f"{profile.expected_drc['violations']} DRC findings and "
                f"{profile.expected_drc['unconnected']} unconnected items remain "
                f"in the {profile.key} baseline"
            ),
        ],
    }


def validate_published_seed(
    profile: SourceProfile,
    artifacts: OutputPaths,
    *,
    seed_path: Path | None = None,
    dsn_path: Path | None = None,
    report_path: Path | None = None,
) -> tuple[Any, dict[str, object], dict[str, object]]:
    seed_path = seed_path or artifacts.seed_board
    dsn_path = dsn_path or artifacts.seed_dsn
    report_path = report_path or artifacts.seed_report
    for path, suffix in (
        (seed_path, ".kicad_pcb"),
        (dsn_path, ".dsn"),
        (report_path, ".json"),
    ):
        require_regular(path, "published R7 seed artifact", suffix)
    report = json.loads(report_path.read_text(encoding="utf-8", errors="strict"))
    if not isinstance(report, dict):
        raise ProbeError("seed report is not an object")
    if (
        report.get("schema") != 1
        or report.get("tool") != Path(__file__).name
        or report.get("tool_sha256") != sha256_file(Path(__file__))
        or report.get("operation_completed") is not True
        or report.get("state") != "R7_FREEROUTING_PROBE_SEED_HOLD"
        or report.get("source_profile") != profile.key
        or report.get("freerouting_executed") is not False
    ):
        raise ProbeError("seed report identity differs")
    outputs = report.get("outputs")
    if not isinstance(outputs, Mapping):
        raise ProbeError("seed report output binding is absent")
    for label, path in (
        ("seed", seed_path),
        ("dsn", dsn_path),
    ):
        record = outputs.get(label)
        published_path = (
            artifacts.seed_board if label == "seed" else artifacts.seed_dsn
        )
        if (
            not isinstance(record, Mapping)
            or record.get("sha256") != sha256_file(path)
            or record.get("bytes") != path.stat().st_size
            or record.get("path") != str(published_path.resolve())
        ):
            raise ProbeError(f"published {label} binding differs")
    source_record = report.get("source")
    if (
        not isinstance(source_record, Mapping)
        or source_record.get("path") != str(profile.source.resolve())
        or source_record.get("bytes") != profile.source.stat().st_size
        or source_record.get("sha256") != profile.sha256
    ):
        raise ProbeError("seed report source binding differs")
    board = load_board(seed_path, "published R7 seed")
    require_seed_locks(board)
    antenna_keepout = require_antenna_keepout(board)
    if report.get("antenna_keepout") != antenna_keepout:
        raise ProbeError("seed report antenna keepout binding differs")
    source = load_board(profile.source, f"frozen {profile.key} source")
    source_geometry = geometry_snapshot(source)
    seed_geometry = geometry_snapshot(board)
    if source_geometry != seed_geometry:
        raise ProbeError(
            f"published seed geometry differs from frozen {profile.key} source"
        )
    dsn_audit = audit_dsn(dsn_path)
    if report.get("dsn_audit") != dsn_audit:
        raise ProbeError("seed report DSN audit binding differs")
    return board, report, dsn_audit


def export_seed(
    *,
    profile: SourceProfile,
    artifacts: OutputPaths,
    kicad_cli: Path,
    kicad_evidence: Mapping[str, object],
    pcbnew_version: str,
    protected: Mapping[str, str],
    dry_run: bool,
) -> dict[str, object]:
    if not dry_run:
        require_output_paths_absent(
            (artifacts.seed_board, artifacts.seed_dsn, artifacts.seed_report)
        )
    source_board = load_board(profile.source, f"frozen {profile.key} source")
    source_geometry = geometry_snapshot(source_board)
    require_expected_source_geometry(source_geometry)
    with tempfile.TemporaryDirectory(prefix="mf1750-r7-freerouting-seed-") as name:
        temporary = Path(name)
        seed = temporary / artifacts.seed_board.name
        dsn = temporary / artifacts.seed_dsn.name
        lock_seed(source_board)
        pcbnew.SaveBoard(str(seed), source_board)
        seed_board = load_board(seed, "temporary R7 seed")
        lock_audit = require_seed_locks(seed_board)
        seed_geometry = geometry_snapshot(seed_board)
        if seed_geometry != source_geometry:
            raise ProbeError(f"locking changed {profile.key} source geometry")
        if not pcbnew.ExportSpecctraDSN(seed_board, str(dsn)):
            raise ProbeError("Specctra DSN export failed")
        seed_hash_after_export = sha256_file(seed)
        dsn_hash_after_export = sha256_file(dsn)
        dsn_audit = audit_dsn(dsn)
        drc = drc_audit(kicad_cli, seed, temporary / "baseline-drc")
        require_frozen_baseline_drc(drc, profile)
        verifier = board_verifier(kicad_cli, seed)
        if (
            sha256_file(seed) != seed_hash_after_export
            or sha256_file(dsn) != dsn_hash_after_export
        ):
            raise ProbeError("validated seed or DSN changed before publication")
        final_seed_board = load_board(seed, "final temporary R7 seed")
        require_seed_locks(final_seed_board)
        antenna_keepout = require_antenna_keepout(final_seed_board)
        if geometry_snapshot(final_seed_board) != source_geometry:
            raise ProbeError("validated seed geometry changed before publication")
        report = seed_report(
            profile=profile,
            source=profile.source,
            seed=seed,
            dsn=dsn,
            geometry=source_geometry["counts"],
            lock_audit=lock_audit,
            antenna_keepout=antenna_keepout,
            dsn_audit=dsn_audit,
            drc=drc,
            verifier=verifier,
            kicad_cli=kicad_evidence,
            pcbnew_version=pcbnew_version,
            dry_run=dry_run,
        )
        assert_protected_unchanged(protected, "after temporary seed validation")
        if not dry_run:
            final_report = dict(report)
            final_report["outputs"] = {
                "seed": {
                    "path": str(artifacts.seed_board.resolve()),
                    "bytes": seed.stat().st_size,
                    "sha256": sha256_file(seed),
                },
                "dsn": {
                    "path": str(artifacts.seed_dsn.resolve()),
                    "bytes": dsn.stat().st_size,
                    "sha256": sha256_file(dsn),
                },
            }
            publish_new_group(
                (
                    (artifacts.seed_board, seed.read_bytes()),
                    (artifacts.seed_dsn, dsn.read_bytes()),
                    (artifacts.seed_report, json_bytes(final_report)),
                ),
                protected,
            )
            report = final_report
        return report


def import_session(
    *,
    profile: SourceProfile,
    artifacts: OutputPaths,
    session: Path,
    kicad_cli: Path,
    kicad_evidence: Mapping[str, object],
    pcbnew_version: str,
    protected: Mapping[str, str],
    dry_run: bool,
) -> dict[str, object]:
    require_regular(session, "Freerouting session", ".ses")
    if session.resolve() in {
        path.resolve()
        for path in (
            *PROTECTED_INPUTS,
            artifacts.seed_board,
            artifacts.seed_dsn,
            artifacts.seed_report,
        )
    }:
        raise ProbeError("SES path aliases a protected input")
    if not dry_run:
        require_output_paths_absent(
            (artifacts.imported_board, artifacts.import_report)
        )
    with tempfile.TemporaryDirectory(prefix="mf1750-r7-freerouting-import-") as name:
        temporary = Path(name)
        working_seed = temporary / artifacts.seed_board.name
        working_dsn = temporary / artifacts.seed_dsn.name
        working_report = temporary / artifacts.seed_report.name
        working_session = temporary / f"supplied_{session.name}"
        candidate = temporary / artifacts.imported_board.name
        seed_record = snapshot_bound_input(
            artifacts.seed_board, working_seed, "published seed", ".kicad_pcb"
        )
        dsn_record = snapshot_bound_input(
            artifacts.seed_dsn, working_dsn, "published DSN", ".dsn"
        )
        seed_report_record = snapshot_bound_input(
            artifacts.seed_report, working_report, "published seed report", ".json"
        )
        session_record = snapshot_bound_input(
            session, working_session, "Freerouting session", ".ses"
        )
        _, published_report, dsn_audit = validate_published_seed(
            profile,
            artifacts,
            seed_path=working_seed,
            dsn_path=working_dsn,
            report_path=working_report,
        )
        board = load_board(working_seed, "temporary R7 seed")
        if not pcbnew.ImportSpecctraSES(board, str(working_session)):
            raise ProbeError("KiCad rejected the supplied Specctra SES")
        pcbnew.SaveBoard(str(candidate), board)
        candidate_hash_after_save = sha256_file(candidate)
        candidate_board = load_board(candidate, "temporary imported candidate")
        if int(candidate_board.GetCopperLayerCount()) != EXPECTED_COUNTS["copper_layers"]:
            raise ProbeError("SES changed the four-layer stack")
        seed_board = load_board(working_seed, "temporary R7 seed for lock audit")
        lock_preservation = require_candidate_lock_preservation(
            seed_board, candidate_board
        )
        protected_region_audit = audit_new_copper_regions(
            seed_board, candidate_board
        )
        preservation = audit_import_preservation(working_seed, candidate)
        baseline_drc = drc_audit(kicad_cli, working_seed, temporary / "baseline-drc")
        require_frozen_baseline_drc(baseline_drc, profile)
        candidate_drc = drc_audit(kicad_cli, candidate, temporary / "candidate-drc")
        progress = require_candidate_drc_progress(baseline_drc, candidate_drc)
        verifier = board_verifier(kicad_cli, candidate)
        if sha256_file(candidate) != candidate_hash_after_save:
            raise ProbeError("imported candidate changed during validation")
        final_candidate_board = load_board(candidate, "final imported candidate")
        repeated_locks = require_candidate_lock_preservation(
            seed_board, final_candidate_board
        )
        repeated_region_audit = audit_new_copper_regions(
            seed_board, final_candidate_board
        )
        repeated_preservation = audit_import_preservation(working_seed, candidate)
        if (
            repeated_locks != lock_preservation
            or repeated_region_audit != protected_region_audit
            or repeated_preservation != preservation
        ):
            raise ProbeError("candidate preservation evidence changed during validation")
        bound_inputs = (
            (artifacts.seed_board, seed_record, "published seed"),
            (artifacts.seed_dsn, dsn_record, "published DSN"),
            (artifacts.seed_report, seed_report_record, "published seed report"),
            (session, session_record, "Freerouting session"),
        )
        for source, record, label in bound_inputs:
            assert_bound_input_unchanged(source, record, label)
        report: dict[str, object] = {
            "schema": 1,
            "tool": Path(__file__).name,
            "tool_sha256": sha256_file(Path(__file__)),
            "generated_at_utc": utc_now(),
            "mode": "REVISION_TO_STAGING_ONLY",
            "state": "R7_FREEROUTING_IMPORTED_CANDIDATE_HOLD",
            "overall_status": "HOLD",
            "operation_completed": True,
            "locally_verified": False,
            "manufacturing_authorized": False,
            "dry_run": dry_run,
            "source_profile": profile.key,
            "source": file_record(profile.source),
            "seed": seed_record,
            "dsn": dsn_record,
            "seed_report": seed_report_record,
            "seed_report_state": published_report["state"],
            "session": session_record,
            "candidate": file_record(candidate),
            "dsn_audit": dsn_audit,
            "lock_preservation": lock_preservation,
            "protected_region_audit": protected_region_audit,
            "preservation": preservation,
            "baseline_drc": baseline_drc,
            "candidate_drc": candidate_drc,
            "drc_progress": progress,
            "board_verifier": verifier,
            "tools": {"pcbnew": pcbnew_version, "kicad_cli": dict(kicad_evidence)},
            "freerouting_executed_by_wrapper": False,
            "network_accessed": False,
            "hardware_accessed": False,
            "formal_board_modified": False,
            "r6_source_modified": False,
            "readme_modified": False,
            "holds": [
                "imported autorouter output remains an engineering candidate",
                "visual, SI, PI, thermal, mechanical and manufacturing reviews remain open",
                "no fabrication or order authorization is implied",
            ],
        }
        assert_protected_unchanged(protected, "after temporary SES validation")
        for source, record, label in bound_inputs:
            assert_bound_input_unchanged(source, record, label)
        if sha256_file(candidate) != candidate_hash_after_save:
            raise ProbeError("candidate changed before publication")
        if not dry_run:
            final_report = dict(report)
            final_report["candidate"] = {
                "path": str(artifacts.imported_board.resolve()),
                "bytes": candidate.stat().st_size,
                "sha256": sha256_file(candidate),
            }
            publish_new_group(
                (
                    (artifacts.import_report, json_bytes(final_report)),
                    # Candidate is linked last so any earlier publication
                    # failure cannot leave a candidate board behind.
                    (artifacts.imported_board, candidate.read_bytes()),
                ),
                protected,
            )
            report = final_report
        return report


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-profile",
        choices=tuple(SOURCE_PROFILES),
        default=DEFAULT_SOURCE_PROFILE,
        help=(
            "hash-pinned source allowlist entry; defaults to r7-hygiene, "
            "with r6-epd retained only as an explicit probe branch"
        ),
    )
    parser.add_argument(
        "--import-session",
        type=Path,
        help="explicit Freerouting .ses to import into the published R7 probe seed",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="perform all applicable work in OS temporary storage; publish nothing",
    )
    parser.add_argument(
        "--kicad-cli",
        type=Path,
        help="explicit KiCad 10.0.3 kicad-cli path",
    )
    return parser.parse_args(argv)


def failure_report(
    mode: str, error: Exception, artifacts: OutputPaths
) -> dict[str, object]:
    known_outputs = (
        (artifacts.import_report, artifacts.imported_board)
        if mode == "IMPORT_SESSION"
        else (artifacts.seed_board, artifacts.seed_dsn, artifacts.seed_report)
    )
    residual_outputs: list[dict[str, object]] = []
    for path in known_outputs:
        if not path.exists() and not path.is_symlink():
            continue
        record: dict[str, object] = {
            "path": str(path.resolve(strict=False)),
            "is_symlink": path.is_symlink(),
            "is_regular_file": path.is_file() and not path.is_symlink(),
        }
        if record["is_regular_file"]:
            record["bytes"] = path.stat().st_size
            record["sha256"] = sha256_file(path)
        residual_outputs.append(record)
    return {
        "schema": 1,
        "tool": Path(__file__).name,
        "generated_at_utc": utc_now(),
        "mode": mode,
        "state": "R7_FREEROUTING_PROBE_FAILED",
        "overall_status": "FAIL",
        "operation_completed": False,
        "locally_verified": False,
        "candidate_written": (
            artifacts.imported_board.exists()
            or artifacts.imported_board.is_symlink()
        ),
        "known_output_residue": residual_outputs,
        "error": f"{type(error).__name__}: {error}",
        "traceback": traceback.format_exc(),
        "freerouting_executed_by_wrapper": False,
        "network_accessed": False,
        "hardware_accessed": False,
    }


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    mode = "IMPORT_SESSION" if args.import_session is not None else "EXPORT_SEED"
    profile = SOURCE_PROFILES[args.source_profile]
    artifacts = output_paths(profile)
    protected: dict[str, str] = {}
    try:
        pcbnew_version = require_pcbnew()
        kicad_cli, kicad_evidence = resolve_kicad_cli(args.kicad_cli)
        require_no_locks()
        protected = protected_snapshot()
        if args.import_session is None:
            report = export_seed(
                profile=profile,
                artifacts=artifacts,
                kicad_cli=kicad_cli,
                kicad_evidence=kicad_evidence,
                pcbnew_version=pcbnew_version,
                protected=protected,
                dry_run=bool(args.dry_run),
            )
        else:
            report = import_session(
                profile=profile,
                artifacts=artifacts,
                session=args.import_session.resolve(),
                kicad_cli=kicad_cli,
                kicad_evidence=kicad_evidence,
                pcbnew_version=pcbnew_version,
                protected=protected,
                dry_run=bool(args.dry_run),
            )
        assert_protected_unchanged(protected, "at wrapper completion")
    except Exception as exc:  # fail closed with stdout evidence only
        report = failure_report(mode, exc, artifacts)
        if protected:
            try:
                assert_protected_unchanged(protected, "after wrapper failure")
            except Exception as source_error:
                report["protected_input_failure"] = (
                    f"{type(source_error).__name__}: {source_error}"
                )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
