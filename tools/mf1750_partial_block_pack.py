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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-passed", type=int, required=True)
    parser.add_argument("--pytest-subtests-passed", type=int, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.pytest_passed < 1 or args.pytest_subtests_passed < 0:
        raise SystemExit("invalid pytest summary")
    if OUT.exists():
        raise SystemExit(f"offline bundle already exists; refusing to overwrite: {OUT}")

    contract = run_checks(ROOT)
    if contract["passed"] is not True:
        raise SystemExit("repository contract is not clean")
    production = _fingerprint(PRODUCTION_BIN)
    if production["sha256"] != PRODUCTION_SHA256:
        raise SystemExit("production firmware zero-diff identity changed")

    # Re-render every generated source and prove the on-disk files are exact.
    rendered = build.render_all()
    for relative, content in rendered.items():
        path = ROOT / relative
        if not path.is_file() or path.read_bytes() != content.encode("utf-8"):
            raise SystemExit(f"generated source drifted before packing: {path}")

    frame_tool = (ROOT / "tools/mf1750_frame_tool.py").read_text(encoding="utf-8")
    api_doc = (ROOT / "docs/MF1750_DRIVER_API.md").read_text(encoding="utf-8")
    platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
    for env, tag in ((build.ATLAS_ENV, build.ATLAS_TAG),
                     (build.PTLW_ENV, build.PTLW_TAG)):
        if f"[env:{env}]" not in platformio:
            raise SystemExit(f"PlatformIO env registration missing: {env}")
        if tag not in frame_tool or tag not in api_doc:
            raise SystemExit(f"tag registration missing: {tag}")
        main_source = rendered[
            "src/partial_atlas_1e_main.cpp" if env == build.ATLAS_ENV
            else "src/partial_block_ptlw_main.cpp"
        ]
        if f'FW_BUILD_TAG = "{tag}"' not in main_source:
            raise SystemExit(f"main TU tag mismatch: {tag}")

    report = build.build_report()
    frame = build.build_atlas_frame()
    if _sha256(frame) != report["route_a"]["frame"]["sha256"]:
        raise SystemExit("route A frame identity drifted")

    firmware: dict[str, dict[str, Any]] = {}
    artifacts: dict[str, bytes] = {}
    for env, stem in ((build.ATLAS_ENV, "partial-atlas-1e"),
                      (build.PTLW_ENV, "partial-block-ptlw")):
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
        "firmware": firmware[build.ATLAS_ENV],
    }
    route_b_doc = {
        "schema_version": 1,
        "kind": "mf1750-partial-block-route-b-generation",
        **report["route_b"],
        "firmware": firmware[build.PTLW_ENV],
    }
    artifacts["route-a-generation.json"] = _pretty(route_a_doc)
    artifacts["route-b-generation.json"] = _pretty(route_b_doc)
    artifacts["partial-atlas-1e-roi-list.json"] = _pretty(
        report["route_a"]["roi_list"]
    )
    artifacts["partial-block-ptlw-roi-list.json"] = _pretty(
        report["route_b"]["roi_list"]
    )
    artifacts["partial-atlas-1e-frame.bin"] = frame

    busy_evidence = (
        "per-action EpdOperationReport (pon/drf/pof wait ms and busy stage "
        "evidence) published via /api/diagnostic/report"
    )
    actions: list[dict[str, Any]] = [
        {
            "ordinal": 0,
            "route": "A",
            "role": "P0_FULL_FRAME_1E_SEVEN_CODE_ATLAS",
            "env": build.ATLAS_ENV,
            "window": None,
            "controllers": ["CS1", "CS2"],
            "dtm_bytes_per_controller": build.CONTROLLER_DTM_BYTES,
            "r20_sha256": report["route_a"]["profile"]["r20_sha256"],
            "frame_sha256": report["route_a"]["frame"]["sha256"],
            "layout_sha256": report["route_a"]["layout"]["sha256"],
            "firmware_sha256": firmware[build.ATLAS_ENV]["bin_sha256"],
            "busy_timeline": busy_evidence,
        }
    ]
    for action in report["route_b"]["actions"]:
        profile = action["profile"]
        actions.append({
            "ordinal": action["ordinal"],
            "route": "B",
            "role": action["role"],
            "env": build.PTLW_ENV,
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
            "firmware_sha256": firmware[build.PTLW_ENV]["bin_sha256"],
            "busy_timeline": busy_evidence,
        })

    files = [
        {"file": name, "bytes": len(payload), "sha256": _sha256(payload)}
        for name, payload in sorted(artifacts.items())
    ]
    manifest = {
        "schema_version": 1,
        "kind": "mf1750-partial-block-first-batch-offline-bundle",
        "batch_id": OUT.name,
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
            "env": build.ATLAS_ENV,
            "tag": build.ATLAS_TAG,
            "profile": report["route_a"]["profile"],
            "frame": report["route_a"]["frame"],
            "layout_sha256": report["route_a"]["layout"]["sha256"],
            "roi_list_file": "partial-atlas-1e-roi-list.json",
            "generation_report": "route-a-generation.json",
            "firmware": firmware[build.ATLAS_ENV],
        },
        "route_b": {
            "env": build.PTLW_ENV,
            "tag": build.PTLW_TAG,
            "profiles": report["route_b"]["profiles"],
            "windows": report["route_b"]["windows"],
            "window_semantics": report["route_b"]["window_semantics"],
            "ptlw": report["route_b"]["ptlw"],
            "transport": report["route_b"]["transport"],
            "roi_list_file": "partial-block-ptlw-roi-list.json",
            "generation_report": "route-b-generation.json",
            "firmware": firmware[build.PTLW_ENV],
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
    unsigned = dict(manifest)
    unsigned.pop("integrity")
    manifest["integrity"]["sha256"] = _sha256(_canonical(unsigned))
    manifest_payload = _pretty(manifest)

    OUT.mkdir(parents=False, exist_ok=False)
    for name, payload in sorted(artifacts.items()):
        _write_new(OUT / name, payload)
    _write_new(OUT / "manifest.json", manifest_payload)

    sealed = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    seal = sealed["integrity"]["sha256"]
    sealed_unsigned = dict(sealed)
    sealed_unsigned.pop("integrity")
    if _sha256(_canonical(sealed_unsigned)) != seal:
        raise SystemExit("manifest self-seal verification failed")
    for entry in sealed["files"]:
        payload = (OUT / entry["file"]).read_bytes()
        if len(payload) != entry["bytes"] or _sha256(payload) != entry["sha256"]:
            raise SystemExit(f"bundle file fingerprint failed: {entry['file']}")

    print(json.dumps({
        "bundle": OUT.relative_to(ROOT).as_posix(),
        "route_a": {
            "env": build.ATLAS_ENV,
            "tag": build.ATLAS_TAG,
            "frame_sha256": report["route_a"]["frame"]["sha256"],
            "layout_sha256": report["route_a"]["layout"]["sha256"],
            "r20_sha256": report["route_a"]["profile"]["r20_sha256"],
            "bin_sha256": firmware[build.ATLAS_ENV]["bin_sha256"],
        },
        "route_b": {
            "env": build.PTLW_ENV,
            "tag": build.PTLW_TAG,
            "profile_r20_sha256": {
                label: report["route_b"]["profiles"][label]["r20_sha256"]
                for label in build.PTLW_PROFILE_LABELS
            },
            "combined_dtm_sha256":
                report["route_b"]["transport"]["combined_dtm"]["sha256"],
            "bin_sha256": firmware[build.PTLW_ENV]["bin_sha256"],
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
