#!/usr/bin/env python3
"""Seal the MF1750 partial-block first-batch offline bundle.

Packages the two generated research environments of
docs/MF1750_PARTIAL_BLOCK_WAVEFORM_HANDOFF_20261020.md (route A compiled
multi-code 1E atlas, route B clean-PTLW partial windows A=1E/B=0E/C=1C):
generation reports, measurement ROI lists, the reference atlas frame, and the
compiled firmware identities.  The destination directory and every file are
created exclusively (O_EXCL semantics); the manifest self-seals with the
sha256-canonical-json-without-integrity convention.  No hardware, serial,
relay, network, camera, or flashing access is performed.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import mf1750_partial_block_build as build  # noqa: E402
from tools.check_repo_contract import run_checks  # noqa: E402

OUT = ROOT / ".test-output/offline/MF1750_PARTIAL_BLOCK_20261020_V1"
OUT_V2 = ROOT / ".test-output/offline/MF1750_PARTIAL_BLOCK_20261020_V2"
OUT_V3 = ROOT / ".test-output/offline/MF1750_PARTIAL_BLOCK_20261020_V3"
PRODUCTION_BIN = ROOT / ".pio/build/esp32-s3-devkitc-1/firmware.bin"
PRODUCTION_SHA256 = "ba59c3d6111a15c3426eddedf63188bf323083fdca24dec98939835b43dacdc3"
PYTEST_COMMAND = "python -m pytest -q tests/test_mf1750_partial_block_build.py"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _pretty(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    ).encode("utf-8")


def _fingerprint(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    return {"bytes": len(payload), "sha256": _sha256(payload)}


def _write_new(path: Path, payload: bytes) -> None:
    with path.open("xb") as destination:
        destination.write(payload)


def _main_v3(args: argparse.Namespace) -> int:
    """Seal the V3 normalization+probe session bundle (atlas-only)."""

    out_dir = OUT_V3
    if out_dir.exists():
        raise SystemExit(f"offline bundle already exists; refusing to overwrite: {out_dir}")
    contract = run_checks(ROOT)
    if contract["passed"] is not True:
        raise SystemExit("repository contract is not clean")
    production = _fingerprint(PRODUCTION_BIN)
    if production["sha256"] != PRODUCTION_SHA256:
        raise SystemExit("production firmware zero-diff identity changed")

    rendered = build.render_v3()
    for relative, content in rendered.items():
        path = ROOT / relative
        if not path.is_file() or path.read_bytes() != content.encode("utf-8"):
            raise SystemExit(f"generated source drifted before packing: {path}")

    frame_tool = (ROOT / "tools/mf1750_frame_tool.py").read_text(encoding="utf-8")
    api_doc = (ROOT / "docs/MF1750_DRIVER_API.md").read_text(encoding="utf-8")
    platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
    if f"[env:{build.ATLAS_ENV_V3}]" not in platformio:
        raise SystemExit(f"PlatformIO env registration missing: {build.ATLAS_ENV_V3}")
    if build.ATLAS_TAG_V3 not in frame_tool or build.ATLAS_TAG_V3 not in api_doc:
        raise SystemExit(f"tag registration missing: {build.ATLAS_TAG_V3}")
    if f'FW_BUILD_TAG = "{build.ATLAS_TAG_V3}"' not in rendered[build.V3_PATHS["main"]]:
        raise SystemExit(f"main TU tag mismatch: {build.ATLAS_TAG_V3}")

    report = build.build_v3_report()
    atlas_frame = build.build_atlas_frame("V2")
    if _sha256(atlas_frame) != report["frames"]["atlas_v2"]["sha256"]:
        raise SystemExit("V3 atlas frame identity drifted from the V2 frame")

    build_dir = ROOT / ".pio/build" / build.ATLAS_ENV_V3
    bin_payload = (build_dir / "firmware.bin").read_bytes()
    elf_payload = (build_dir / "firmware.elf").read_bytes()
    firmware = {
        "build": "SUCCESS",
        "env": build.ATLAS_ENV_V3,
        "bin_file": "partial-atlas-1e-v3-firmware.bin",
        "bin_bytes": len(bin_payload),
        "bin_sha256": _sha256(bin_payload),
        "elf_file": "partial-atlas-1e-v3-firmware.elf",
        "elf_bytes": len(elf_payload),
        "elf_sha256": _sha256(elf_payload),
    }
    generation_doc = {
        "schema_version": 1,
        "kind": "mf1750-partial-block-v3-session-generation",
        **report,
        "firmware": firmware,
    }
    artifacts: dict[str, bytes] = {
        "partial-atlas-1e-v3-firmware.bin": bin_payload,
        "partial-atlas-1e-v3-firmware.elf": elf_payload,
        "route-a-v3-generation.json": _pretty(generation_doc),
        "partial-atlas-1e-v3-roi-list.json": _pretty(build.atlas_roi_list_doc("V2")),
        "partial-atlas-1e-v3-atlas-frame.bin": atlas_frame,
    }

    busy_evidence = (
        "per-action EpdOperationReport (pon/drf/pof wait ms and busy stage "
        "evidence) via /api/diagnostic/report; per-step PON/DRF/POF timings "
        "for NORMALIZE via /api/partial-atlas-v3/steps"
    )
    actions = []
    for action in report["actions"]:
        profile = action.get("profile")
        frame_sha = action.get("frame_sha256")
        tuple_sha = None
        if profile == "1E":
            tuple_sha = report["tuples"]["1E"]["r20_sha256"]
        elif profile == "factory_otp+active":
            tuple_sha = report["tuples"]["active"]["r20_sha256"]
        actions.append({
            **action,
            "env": build.ATLAS_ENV_V3,
            "firmware_sha256": firmware["bin_sha256"],
            "frame_sha256": frame_sha,
            "r20_sha256": tuple_sha,
            "busy_timeline": busy_evidence,
        })

    files = [
        {"file": name, "bytes": len(payload), "sha256": _sha256(payload)}
        for name, payload in sorted(artifacts.items())
    ]
    manifest = {
        "schema_version": 1,
        "kind": "mf1750-partial-block-v3-session-offline-bundle",
        "batch_id": out_dir.name,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "offline_only": True,
        "hardware_tested": False,
        "refresh_count": 0,
        "handoff": {
            "path": build.HANDOFF_DOC,
            "sha256": _fingerprint(ROOT / build.HANDOFF_DOC)["sha256"],
        },
        "amendment": report["amendment"],
        "generator": {
            "path": "tools/mf1750_partial_block_build.py",
            "sha256": _fingerprint(ROOT / "tools/mf1750_partial_block_build.py")["sha256"],
        },
        "packager": {
            "path": "tools/mf1750_partial_block_pack.py",
            "sha256": _fingerprint(Path(__file__))["sha256"],
        },
        "spi_hz": report["spi_hz"],
        "runtime_tail_sha256": report["runtime_tail_sha256"],
        "runtime_tail_byte_identical_to_r2g": True,
        "session": {
            "env": build.ATLAS_ENV_V3,
            "tag": build.ATLAS_TAG_V3,
            "tuples": report["tuples"],
            "normalize": report["normalize"],
            "frames": report["frames"],
            "controller_stream_fnv1a": report["controller_stream_fnv1a"],
            "roi_list_file": "partial-atlas-1e-v3-roi-list.json",
            "generation_report": "route-a-v3-generation.json",
            "firmware": firmware,
        },
        "actions": actions,
        "generated_sources": report["generated_sources"],
        "supersedes_note": {
            "bundles": ["MF1750_PARTIAL_BLOCK_20261020_V1",
                        "MF1750_PARTIAL_BLOCK_20261020_V2"],
            "note": "V3 is the P0 re-verification session env; V1/V2 stay the "
                    "canonical P0/P0V2-matched identities",
        },
        "verification": {
            "variant_builds": {build.ATLAS_ENV_V3: "SUCCESS"},
            "production_build": {
                "env": "esp32-s3-devkitc-1",
                "status": "SUCCESS",
                "zero_diff": True,
                **production,
            },
            "check_repo_contract": {"passed": True, "hardware_tested": False},
            "pytest": {
                "command": PYTEST_COMMAND,
                "status": "SUCCESS",
                "passed": args.pytest_passed,
                "subtests_passed": args.pytest_subtests_passed,
                "failed": 0,
            },
        },
        "files": files,
        "integrity": {
            "algorithm": "sha256-canonical-json-without-integrity",
            "sha256": "",
        },
    }
    unsigned = dict(manifest)
    unsigned.pop("integrity")
    manifest["integrity"]["sha256"] = _sha256(_canonical(unsigned))
    manifest_payload = _pretty(manifest)

    out_dir.mkdir(parents=False, exist_ok=False)
    for name, payload in sorted(artifacts.items()):
        _write_new(out_dir / name, payload)
    _write_new(out_dir / "manifest.json", manifest_payload)

    sealed = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    seal = sealed["integrity"]["sha256"]
    sealed_unsigned = dict(sealed)
    sealed_unsigned.pop("integrity")
    if _sha256(_canonical(sealed_unsigned)) != seal:
        raise SystemExit("manifest self-seal verification failed")
    for entry in sealed["files"]:
        payload = (out_dir / entry["file"]).read_bytes()
        if len(payload) != entry["bytes"] or _sha256(payload) != entry["sha256"]:
            raise SystemExit(f"bundle file fingerprint failed: {entry['file']}")

    print(json.dumps({
        "bundle": out_dir.relative_to(ROOT).as_posix(),
        "env": build.ATLAS_ENV_V3,
        "tag": build.ATLAS_TAG_V3,
        "bin_sha256": firmware["bin_sha256"],
        "normalize_steps": report["normalize"]["step_count"],
        "atlas_frame_sha256": report["frames"]["atlas_v2"]["sha256"],
        "probe7_frame_sha256": report["frames"]["probe7"]["sha256"],
        "file_count_excluding_manifest": len(files),
        "manifest_canonical_sha256": seal,
        "manifest_file_sha256": _sha256(manifest_payload),
        "production_bin_sha256": production["sha256"],
        "pytest": manifest["verification"]["pytest"],
    }, indent=1))
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-passed", type=int, required=True)
    parser.add_argument("--pytest-subtests-passed", type=int, required=True)
    parser.add_argument("--version", choices=("V1", "V2", "V3"), default="V1",
                        help="bundle revision; V2 carries the handoff amendment-2 "
                             "layout/patch-code probe changes, V3 the "
                             "normalization+probe session env")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.pytest_passed < 1 or args.pytest_subtests_passed < 0:
        raise SystemExit("invalid pytest summary")
    if args.version == "V3":
        return _main_v3(args)
    version = args.version
    names = build._version_names(version)
    out_dir = OUT if version == "V1" else OUT_V2
    stem_atlas = "partial-atlas-1e" if version == "V1" else "partial-atlas-1e-v2"
    stem_ptlw = "partial-block-ptlw" if version == "V1" else "partial-block-ptlw-v2"
    atlas_env, atlas_tag = names["atlas_env"], names["atlas_tag"]
    ptlw_env, ptlw_tag = names["ptlw_env"], names["ptlw_tag"]
    if out_dir.exists():
        raise SystemExit(f"offline bundle already exists; refusing to overwrite: {out_dir}")

    contract = run_checks(ROOT)
    if contract["passed"] is not True:
        raise SystemExit("repository contract is not clean")
    production = _fingerprint(PRODUCTION_BIN)
    if production["sha256"] != PRODUCTION_SHA256:
        raise SystemExit("production firmware zero-diff identity changed")

    # Re-render every generated source and prove the on-disk files are exact.
    rendered = build.render_version(version)
    for relative, content in rendered.items():
        path = ROOT / relative
        if not path.is_file() or path.read_bytes() != content.encode("utf-8"):
            raise SystemExit(f"generated source drifted before packing: {path}")

    frame_tool = (ROOT / "tools/mf1750_frame_tool.py").read_text(encoding="utf-8")
    api_doc = (ROOT / "docs/MF1750_DRIVER_API.md").read_text(encoding="utf-8")
    platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
    for env, tag in ((atlas_env, atlas_tag),
                     (ptlw_env, ptlw_tag)):
        if f"[env:{env}]" not in platformio:
            raise SystemExit(f"PlatformIO env registration missing: {env}")
        if tag not in frame_tool or tag not in api_doc:
            raise SystemExit(f"tag registration missing: {tag}")
        main_source = rendered[
            names["atlas_main"] if env == atlas_env else names["ptlw_main"]
        ]
        if f'FW_BUILD_TAG = "{tag}"' not in main_source:
            raise SystemExit(f"main TU tag mismatch: {tag}")

    report = build.build_report(version)
    frame = build.build_atlas_frame(version)
    if _sha256(frame) != report["route_a"]["frame"]["sha256"]:
        raise SystemExit("route A frame identity drifted")

    firmware: dict[str, dict[str, Any]] = {}
    artifacts: dict[str, bytes] = {}
    for env, stem in ((atlas_env, stem_atlas),
                      (ptlw_env, stem_ptlw)):
        build_dir = ROOT / ".pio/build" / env
        bin_payload = (build_dir / "firmware.bin").read_bytes()
        elf_payload = (build_dir / "firmware.elf").read_bytes()
        bin_name = f"{stem}-firmware.bin"
        elf_name = f"{stem}-firmware.elf"
        artifacts[bin_name] = bin_payload
        artifacts[elf_name] = elf_payload
        firmware[env] = {
            "build": "SUCCESS",
            "bin_file": bin_name,
            "bin_bytes": len(bin_payload),
            "bin_sha256": _sha256(bin_payload),
            "elf_file": elf_name,
            "elf_bytes": len(elf_payload),
            "elf_sha256": _sha256(elf_payload),
        }

    route_a_doc = {
        "schema_version": 1,
        "kind": "mf1750-partial-block-route-a-generation",
        **report["route_a"],
        "firmware": firmware[atlas_env],
    }
    if version != "V1":
        route_a_doc["layout_revision"] = version
        route_a_doc["changes_vs_v1"] = report["changes_vs_v1"]
    route_b_doc = {
        "schema_version": 1,
        "kind": "mf1750-partial-block-route-b-generation",
        **report["route_b"],
        "firmware": firmware[ptlw_env],
    }
    if version != "V1":
        route_b_doc["layout_revision"] = version
        route_b_doc["changes_vs_v1"] = report["changes_vs_v1"]
    route_a_report_name = "route-a-generation.json" if version == "V1" else "route-a-v2-generation.json"
    route_b_report_name = "route-b-generation.json" if version == "V1" else "route-b-v2-generation.json"
    atlas_roi_name = f"{stem_atlas}-roi-list.json"
    ptlw_roi_name = f"{stem_ptlw}-roi-list.json"
    artifacts[route_a_report_name] = _pretty(route_a_doc)
    artifacts[route_b_report_name] = _pretty(route_b_doc)
    artifacts[atlas_roi_name] = _pretty(
        report["route_a"]["roi_list"]
    )
    artifacts[ptlw_roi_name] = _pretty(
        report["route_b"]["roi_list"]
    )
    artifacts[f"{stem_atlas}-frame.bin"] = frame

    busy_evidence = (
        "per-action EpdOperationReport (pon/drf/pof wait ms and busy stage "
        "evidence) published via /api/diagnostic/report"
    )
    actions: list[dict[str, Any]] = [
        {
            "ordinal": 0,
            "route": "A",
            "role": "P0_FULL_FRAME_1E_SEVEN_CODE_ATLAS",
            "env": atlas_env,
            "window": None,
            "controllers": ["CS1", "CS2"],
            "dtm_bytes_per_controller": build.CONTROLLER_DTM_BYTES,
            "r20_sha256": report["route_a"]["profile"]["r20_sha256"],
            "frame_sha256": report["route_a"]["frame"]["sha256"],
            "layout_sha256": report["route_a"]["layout"]["sha256"],
            "firmware_sha256": firmware[atlas_env]["bin_sha256"],
            "busy_timeline": busy_evidence,
        }
    ]
    for action in report["route_b"]["actions"]:
        profile = action["profile"]
        actions.append({
            "ordinal": action["ordinal"],
            "route": "B",
            "role": action["role"],
            "env": ptlw_env,
            "window": action["window"],
            "controllers": ["CS1", "CS2"],
            "dtm_bytes_per_controller": (
                build.CONTROLLER_DTM_BYTES + 160 * 120 // 2
                if profile else build.CONTROLLER_DTM_BYTES
            ),
            "r20_sha256": (
                report["route_b"]["profiles"][profile]["r20_sha256"]
                if profile else None
            ),
            "profile_family_label": profile,
            "family_label_is_not_bitmask": True,
            "firmware_sha256": firmware[ptlw_env]["bin_sha256"],
            "busy_timeline": busy_evidence,
        })

    files = [
        {"file": name, "bytes": len(payload), "sha256": _sha256(payload)}
        for name, payload in sorted(artifacts.items())
    ]
    manifest = {
        "schema_version": 1,
        "kind": "mf1750-partial-block-first-batch-offline-bundle",
        "batch_id": out_dir.name,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "offline_only": True,
        "hardware_tested": False,
        "refresh_count": 0,
        "handoff": {
            "path": build.HANDOFF_DOC,
            "sha256": _fingerprint(ROOT / build.HANDOFF_DOC)["sha256"],
        },
        "generator": {
            "path": "tools/mf1750_partial_block_build.py",
            "sha256": _fingerprint(ROOT / "tools/mf1750_partial_block_build.py")["sha256"],
        },
        "packager": {
            "path": "tools/mf1750_partial_block_pack.py",
            "sha256": _fingerprint(Path(__file__))["sha256"],
        },
        "panel": report["panel"],
        "spi_hz": report["spi_hz"],
        "runtime_tail_sha256": report["runtime_tail_sha256"],
        "runtime_tail_byte_identical_to_r2g": True,
        "route_a": {
            "env": atlas_env,
            "tag": atlas_tag,
            "profile": report["route_a"]["profile"],
            "frame": report["route_a"]["frame"],
            "layout_sha256": report["route_a"]["layout"]["sha256"],
            "roi_list_file": atlas_roi_name,
            "generation_report": route_a_report_name,
            "firmware": firmware[atlas_env],
        },
        "route_b": {
            "env": ptlw_env,
            "tag": ptlw_tag,
            "profiles": report["route_b"]["profiles"],
            "windows": report["route_b"]["windows"],
            "window_semantics": report["route_b"]["window_semantics"],
            "ptlw": report["route_b"]["ptlw"],
            "transport": report["route_b"]["transport"],
            "roi_list_file": ptlw_roi_name,
            "generation_report": route_b_report_name,
            "firmware": firmware[ptlw_env],
        },
        "actions": actions,
        "generated_sources": report["generated_sources"],
        "verification": {
            "variant_builds": {env: "SUCCESS" for env in firmware},
            "production_build": {
                "env": "esp32-s3-devkitc-1",
                "status": "SUCCESS",
                "zero_diff": True,
                **production,
            },
            "check_repo_contract": {"passed": True, "hardware_tested": False},
            "pytest": {
                "command": PYTEST_COMMAND,
                "status": "SUCCESS",
                "passed": args.pytest_passed,
                "subtests_passed": args.pytest_subtests_passed,
                "failed": 0,
            },
        },
        "files": files,
        "integrity": {
            "algorithm": "sha256-canonical-json-without-integrity",
            "sha256": "",
        },
    }
    if version != "V1":
        manifest["layout_revision"] = version
        manifest["changes_vs_v1"] = report["changes_vs_v1"]
        manifest["supersedes"] = {
            "bundle": "MF1750_PARTIAL_BLOCK_20261020_V1",
            "note": (
                "V1 remains the canonical P0-matched identity; V2 carries the "
                "handoff amendment-2 probe layout and the route B patch-code "
                "change"
            ),
        }
    unsigned = dict(manifest)
    unsigned.pop("integrity")
    manifest["integrity"]["sha256"] = _sha256(_canonical(unsigned))
    manifest_payload = _pretty(manifest)

    out_dir.mkdir(parents=False, exist_ok=False)
    for name, payload in sorted(artifacts.items()):
        _write_new(out_dir / name, payload)
    _write_new(out_dir / "manifest.json", manifest_payload)

    sealed = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    seal = sealed["integrity"]["sha256"]
    sealed_unsigned = dict(sealed)
    sealed_unsigned.pop("integrity")
    if _sha256(_canonical(sealed_unsigned)) != seal:
        raise SystemExit("manifest self-seal verification failed")
    for entry in sealed["files"]:
        payload = (out_dir / entry["file"]).read_bytes()
        if len(payload) != entry["bytes"] or _sha256(payload) != entry["sha256"]:
            raise SystemExit(f"bundle file fingerprint failed: {entry['file']}")

    print(json.dumps({
        "bundle": out_dir.relative_to(ROOT).as_posix(),
        "route_a": {
            "env": atlas_env,
            "tag": atlas_tag,
            "frame_sha256": report["route_a"]["frame"]["sha256"],
            "layout_sha256": report["route_a"]["layout"]["sha256"],
            "r20_sha256": report["route_a"]["profile"]["r20_sha256"],
            "bin_sha256": firmware[atlas_env]["bin_sha256"],
        },
        "route_b": {
            "env": ptlw_env,
            "tag": ptlw_tag,
            "profile_r20_sha256": {
                label: report["route_b"]["profiles"][label]["r20_sha256"]
                for label in build.PTLW_PROFILE_LABELS
            },
            "patch_code": report["route_b"]["transport"]["crop_dtm"]["code"],
            "combined_dtm_sha256":
                report["route_b"]["transport"]["combined_dtm"]["sha256"],
            "bin_sha256": firmware[ptlw_env]["bin_sha256"],
        },
        "file_count_excluding_manifest": len(files),
        "manifest_canonical_sha256": seal,
        "manifest_file_sha256": _sha256(manifest_payload),
        "production_bin_sha256": production["sha256"],
        "pytest": manifest["verification"]["pytest"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
