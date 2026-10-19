#!/usr/bin/env python3
"""Seal prebuilt WF WMASK firmware variants into an offline bundle.

By default this seals the original 12 low-4-bit variants.  With --group-add it
seals the GrayExt family 1E/1C/1D: a low-4-bit base plus the whole White
records 0-3 group.  With --single-record-add it seals 0E_R0/0E_R1/0E_R2/0E_R3:
base 0E plus exactly one records 0-3 member.  Family labels are not
reinterpreted as bitmasks.  The destination directory and every file are
created exclusively.  No device, network, relay, camera, serial, or flashing
access is performed.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import mf1750_wf_wmask_build as build  # noqa: E402
from tools.check_repo_contract import run_checks  # noqa: E402

OUT = ROOT / ".test-output/offline/WF_WMASK_BUNDLES_20261018_V1"
GRAYEXT_OUT = ROOT / ".test-output/offline/WF_WMASK_GRAYEXT_BUNDLES_20261019_V1"
SINGLE_RECORD_ADD_OUT = ROOT / ".test-output/offline/WF_WMASK_0E_R0TO3_BUNDLES_20261019_V1"
PRODUCTION_BIN = ROOT / ".pio/build/esp32-s3-devkitc-1/firmware.bin"
PRODUCTION_SHA256 = "ba59c3d6111a15c3426eddedf63188bf323083fdca24dec98939835b43dacdc3"
PYTEST_COMMAND = (
    "python -m pytest -q tests/test_mf1750_wf_wmask_build.py "
    "tests/test_frame_tool.py tests/test_repo_contract.py "
    "tests/test_runtime_waveform_contract.py "
    "tests/test_runtime_waveform_l535_table_builder.py "
    "tests/test_runtime_waveform_campaign.py "
    "tests/test_runtime_waveform_evidence.py "
    "tests/test_runtime_waveform_execution_plan.py "
    "tests/test_runtime_waveform_seed_perturbation.py "
    "tests/test_runtime_waveform_transport_state_machine.py"
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(payload: dict) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _pretty(payload: dict) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8")


def _fingerprint(path: Path) -> dict:
    payload = path.read_bytes()
    return {"bytes": len(payload), "sha256": _sha256(payload)}


def _write_new(path: Path, payload: bytes) -> None:
    with path.open("xb") as destination:
        destination.write(payload)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-passed", type=int, required=True)
    parser.add_argument("--pytest-subtests-passed", type=int, required=True)
    parser.add_argument(
        "--group-add",
        action="store_true",
        help="seal GrayExt 1E/1C/1D instead of the original 12 low-4-bit variants",
    )
    parser.add_argument(
        "--single-record-add",
        action="store_true",
        help="seal 0E_R0/0E_R1/0E_R2/0E_R3 instead of the other variant families",
    )
    args = parser.parse_args(argv)
    if args.group_add and args.single_record_add:
        parser.error("--group-add and --single-record-add are mutually exclusive")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.pytest_passed < 1 or args.pytest_subtests_passed < 0:
        raise SystemExit("invalid pytest summary")
    if args.single_record_add:
        output_dir = SINGLE_RECORD_ADD_OUT
        variant_specs = [
            (build.SINGLE_RECORD_ADD_BASE_MASK, False, record_add)
            for record_add in build.SINGLE_RECORD_ADD_RECORDS
        ]
    elif args.group_add:
        output_dir = GRAYEXT_OUT
        variant_specs = [(mask, True, None) for mask in build.GRAYEXT_BASE_MASKS]
    else:
        output_dir = OUT
        variant_specs = [(mask, False, None) for mask in build.PENDING_MASKS]
    expected_count = len(variant_specs)
    if output_dir.exists():
        raise SystemExit(f"offline bundle already exists; refusing to overwrite: {output_dir}")
    contract = run_checks(ROOT)
    if contract["passed"] is not True:
        raise SystemExit("repository contract is not clean")
    production = _fingerprint(PRODUCTION_BIN)
    if production["sha256"] != PRODUCTION_SHA256:
        raise SystemExit("production firmware zero-diff identity changed")

    frame_tool = (ROOT / "tools/mf1750_frame_tool.py").read_text(encoding="utf-8")
    api_doc = (ROOT / "docs/MF1750_DRIVER_API.md").read_text(encoding="utf-8")
    platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
    artifacts: dict[str, bytes] = {}
    combinations = []
    for mask, group_add, record_add in variant_specs:
        label = build.family_label(mask, group_add, record_add)
        lower = label.lower()
        report, rendered = build.build_offline_variant(mask, group_add, record_add)
        paths = build.source_paths(mask, group_add, record_add)
        for kind, path in paths.items():
            if path.read_bytes() != rendered[kind].encode("utf-8"):
                raise SystemExit(f"generated source drifted before packing: {path}")
        env = build.env_name(mask, group_add, record_add)
        tag = build.tag(mask, group_add, record_add)
        if tag not in frame_tool or tag not in api_doc:
            raise SystemExit(f"tag registration missing: {tag}")
        if f"[env:{env}]" not in platformio:
            raise SystemExit(f"PlatformIO env registration missing: {env}")
        if f'FW_BUILD_TAG = "{tag}"' not in rendered["main"]:
            raise SystemExit(f"main TU tag mismatch: {tag}")

        build_dir = ROOT / ".pio/build" / env
        firmware_bin = (build_dir / "firmware.bin").read_bytes()
        firmware_elf = (build_dir / "firmware.elf").read_bytes()
        bin_name = f"wf-wmask-{lower}-firmware.bin"
        elf_name = f"wf-wmask-{lower}-firmware.elf"
        report_name = f"wf-wmask-{lower}-generation.json"
        artifacts[bin_name] = firmware_bin
        artifacts[elf_name] = firmware_elf
        report["firmware"] = {
            "build": "SUCCESS",
            "env": env,
            "tag": tag,
            "bin_file": bin_name,
            "bin_bytes": len(firmware_bin),
            "bin_sha256": _sha256(firmware_bin),
            "elf_file": elf_name,
            "elf_bytes": len(firmware_elf),
            "elf_sha256": _sha256(firmware_elf),
        }
        artifacts[report_name] = _pretty(report)
        combination = {
            "mask_hex": report["mask_hex"],
            "commented_records": build.selected_records(mask, group_add, record_add),
            "tag": tag,
            "env": env,
            "build": "SUCCESS",
            "r20_sha256": report["r20_sha256"],
            "pwr_sha256": report["pwr_sha256"],
            "pll_sha256": report["pll_sha256"],
            "r21_sha256": report["r21_sha256"],
            "diff_byte_count_vs_active": report["diff_byte_count_vs_active"],
            "firmware_bin": {
                "file": bin_name,
                "bytes": len(firmware_bin),
                "sha256": _sha256(firmware_bin),
            },
            "firmware_elf": {
                "file": elf_name,
                "bytes": len(firmware_elf),
                "sha256": _sha256(firmware_elf),
            },
            "generation_report": report_name,
            "sources": {
                kind: {
                    "path": path.relative_to(ROOT).as_posix(),
                    "sha256": _sha256(path.read_bytes()),
                }
                for kind, path in paths.items()
            },
        }
        if group_add:
            combination.update({
                "family_label": label,
                "base_mask_hex": report["mask_hex"],
                "records0_3_group_add": True,
                "family_label_is_not_bitmask": True,
                "expected_diff_byte_count_vs_active": report["expected_diff_byte_count_vs_active"],
                "expected_r20_sha256": report["expected_r20_sha256"],
            })
        elif record_add is not None:
            combination.update({
                "family_label": label,
                "base_mask_hex": report["mask_hex"],
                "single_record_add": record_add,
                "family_label_is_not_bitmask": True,
                "expected_diff_byte_count_vs_active": report["expected_diff_byte_count_vs_active"],
                "expected_r20_sha256": report["expected_r20_sha256"],
            })
        combinations.append(combination)

    if len(combinations) != expected_count:
        raise SystemExit(f"WMASK combination count is not exactly {expected_count}")
    if len({item["r20_sha256"] for item in combinations}) != expected_count:
        raise SystemExit("WMASK R20 identities are not unique")
    if len({item["firmware_bin"]["sha256"] for item in combinations}) != expected_count:
        raise SystemExit("WMASK firmware identities are not unique")

    files = [
        {"file": name, "bytes": len(payload), "sha256": _sha256(payload)}
        for name, payload in sorted(artifacts.items())
    ]
    if args.single_record_add:
        enumeration = {
            "pending_count": len(build.SINGLE_RECORD_ADD_RECORDS),
            "family_labels": [
                build.family_label(build.SINGLE_RECORD_ADD_BASE_MASK, False, record_add)
                for record_add in build.SINGLE_RECORD_ADD_RECORDS
            ],
            "base_mask": f"0x{build.mask_label(build.SINGLE_RECORD_ADD_BASE_MASK)}",
            "record_add_values": list(build.SINGLE_RECORD_ADD_RECORDS),
            "family_label_semantics": (
                "family label = base 0E plus exactly one records 0-3 member; "
                "not a bitmask"
            ),
        }
    elif args.group_add:
        enumeration = {
            "pending_count": len(build.GRAYEXT_BASE_MASKS),
            "family_labels": [
                build.family_label(mask, True) for mask in build.GRAYEXT_BASE_MASKS
            ],
            "base_masks": [
                f"0x{build.mask_label(mask)}" for mask in build.GRAYEXT_BASE_MASKS
            ],
            "group_add_records": sorted(build.GROUP_ADD_RECORDS),
            "family_label_semantics": (
                "family label = low-4-bit base plus the whole records 0-3 group; "
                "not an 8-bit bitmask"
            ),
        }
    else:
        enumeration = {
            "total_4bit_masks": 16,
            "pending_count": 12,
            "pending_masks": [f"0x{build.mask_label(mask)}" for mask in build.PENDING_MASKS],
            "excluded": {
                f"0x{mask:02X}": reason for mask, reason in sorted(build.EXCLUDED_MASKS.items())
            },
        }
    manifest = {
        "schema_version": 1,
        "kind": (
            "mf1750-wf-wmask-single-record-add-offline-bundle-batch"
            if args.single_record_add
            else "mf1750-wf-wmask-grayext-offline-bundle-batch"
            if args.group_add else "mf1750-wf-wmask-offline-bundle-batch"
        ),
        "batch_id": output_dir.name,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "offline_only": True,
        "hardware_tested": False,
        "refresh_count": 0,
        "mask_bit_mapping": {"bit0": 4, "bit1": 5, "bit2": 6, "bit3": 7},
        "combination_enumeration": enumeration,
        "generator": {
            "path": "tools/mf1750_wf_wmask_build.py",
            "sha256": _fingerprint(ROOT / "tools/mf1750_wf_wmask_build.py")["sha256"],
        },
        "packager": {
            "path": "tools/mf1750_wf_wmask_pack.py",
            "sha256": _fingerprint(Path(__file__))["sha256"],
        },
        "table_contract": {
            "r20_bytes": 535,
            "white_category": [183, 271],
            "record_bytes": 11,
            "record_i_start": "183 + 11*i",
            "selected_records": "exactly commented",
            "all_other_r20_bytes": "exactly active",
            "pwr": "exactly active and mirrored to R20[1:5]",
            "pll": "exactly active 0x02 and mirrored to R20[6]",
            "r21": "active 704 x 0xFF, unchanged",
            "psr_and_runtime": "driver tail byte-identical to pinned R2G active path",
        },
        "combinations": combinations,
        "verification": {
            "variant_builds": {item["env"]: "SUCCESS" for item in combinations},
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
    if args.single_record_add:
        manifest["single_record_add"] = {
            "enabled": True,
            "base_mask": f"0x{build.mask_label(build.SINGLE_RECORD_ADD_BASE_MASK)}",
            "record_add_values": list(build.SINGLE_RECORD_ADD_RECORDS),
            "family_labels_are_not_bitmasks": True,
        }
    elif args.group_add:
        manifest["records0_3_group_add"] = {
            "enabled": True,
            "records": sorted(build.GROUP_ADD_RECORDS),
            "family_labels_are_not_bitmasks": True,
        }
    unsigned = dict(manifest)
    unsigned.pop("integrity")
    manifest["integrity"]["sha256"] = _sha256(_canonical(unsigned))
    manifest_payload = _pretty(manifest)

    output_dir.mkdir(parents=False, exist_ok=False)
    for name, payload in sorted(artifacts.items()):
        _write_new(output_dir / name, payload)
    _write_new(output_dir / "manifest.json", manifest_payload)

    sealed = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    seal = sealed["integrity"]["sha256"]
    sealed_unsigned = dict(sealed)
    sealed_unsigned.pop("integrity")
    if _sha256(_canonical(sealed_unsigned)) != seal:
        raise SystemExit("manifest self-seal verification failed")
    for entry in sealed["files"]:
        payload = (output_dir / entry["file"]).read_bytes()
        if len(payload) != entry["bytes"] or _sha256(payload) != entry["sha256"]:
            raise SystemExit(f"bundle file fingerprint failed: {entry['file']}")

    print(json.dumps({
        "bundle": output_dir.relative_to(ROOT).as_posix(),
        "combinations": [
            {
                "label": item.get("family_label", item["mask_hex"]),
                "base_mask": item["mask_hex"],
                "records": item["commented_records"],
                "tag": item["tag"],
                "r20_sha256": item["r20_sha256"],
                "bin_sha256": item["firmware_bin"]["sha256"],
            }
            for item in combinations
        ],
        "file_count_excluding_manifest": len(files),
        "manifest_canonical_sha256": seal,
        "manifest_file_sha256": _sha256(manifest_payload),
        "production_bin_sha256": production["sha256"],
        "pytest": manifest["verification"]["pytest"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
