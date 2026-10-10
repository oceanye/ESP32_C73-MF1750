#!/usr/bin/env python3
"""Materialize and validate the reference-first complete-535 LUT release."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_runtime_lut_contract as contract  # noqa: E402
from tools import mf1750_ec5_runtime_lut_physical_once as physical  # noqa: E402
from tools.mf1750_ec5_runtime_lut_compiled_identity import (  # noqa: E402
    _binary_elf_link,
)


KIND = "mf1750-stage3-reference-535-matrix-release"
BUILD_ROOT = Path(".pio/build-reference-535-matrix")
CANDIDATE_SOURCE = Path("src/ec5_reference_field_candidate.inc")
GENERATED_INCLUDE = Path("src/generated/spd1657_legacy_535_reference.inc")
SOURCE_FILES = (
    CANDIDATE_SOURCE,
    GENERATED_INCLUDE,
    Path("src/ec5_pure_field_treatment_identity.inc"),
    Path("src/ec5_pure_field_white_identity.inc"),
    Path("src/ec5_dual_r20_h20_driver.inc"),
    Path("src/ec5_dual_r20_h20_main.cpp"),
    Path("src/ec5_dual_r20_h20_white_main.cpp"),
    Path("tools/mf1750_spd1657_legacy_reference_include.py"),
    Path("tools/mf1750_pure_field_matrix_once.py"),
    Path("platformio.reference_535_matrix.ini"),
)
FRAME_SHA256 = "d2c08f7986ded9dc3bba93970cba7659ff773b36b3564cdfa3325bca4d8e970f"
CS1_SHA256 = "b7239abe691da62db38801bb991d3a118436cdd3f8df8292620aa4f916b5fe25"
CS2_SHA256 = "bc97286c2ade130c8742c5fc174c32a799740f4a9f79446a24eccfd0565251e2"


class PackError(ValueError):
    """A source identity, artifact, or release seal differs."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _defines() -> list[dict[str, str]]:
    text = CANDIDATE_SOURCE.read_text(encoding="utf-8")
    starts = list(
        re.finditer(
            r"^#(?:if|elif) MF1750_REFERENCE_FIELD_CANDIDATE == ([01])$",
            text,
            re.MULTILINE,
        )
    )
    if [int(item.group(1)) for item in starts] != [0, 1]:
        raise PackError("reference candidate source does not contain exact indices 0,1")
    result: list[dict[str, str]] = []
    for position, match in enumerate(starts):
        end = starts[position + 1].start() if position == 0 else text.index("#else", match.end())
        block = text[match.end() : end]
        values = dict(re.findall(r'^#define (PF_[A-Z_]+)\s+"([^"]+)"$', block, re.MULTILINE))
        required = {
            "PF_NAME",
            "PF_NAME_LOWER",
            "PF_GLOBAL_HEADER_PROFILE",
            "PF_EXPECTED_PROFILE",
            "PF_CONTRACT",
            "PF_TREAT_BUILD_TAG",
            "PF_TREAT_TEST_ID",
            "PF_TREAT_NVS_NAMESPACE",
            "PF_RELEASE_REVISION",
            "PF_TREAT_DESCRIPTOR",
            "PF_TREAT_ACTION",
            "PF_WHITE_DESCRIPTOR",
            "PF_WHITE_ACTION",
        }
        if set(values) != required:
            raise PackError(f"reference candidate {position} identity fields differ")
        values["index"] = str(position)
        result.append(values)
    return result


def _artifact(environment: str, descriptor: str, profile: str, role: str) -> dict[str, Any]:
    folder = BUILD_ROOT / environment
    binary = folder / "firmware.bin"
    elf = folder / "firmware.elf"
    if not binary.is_file() or not elf.is_file() or binary.is_symlink() or elf.is_symlink():
        raise PackError(f"{environment} build artifacts are absent or unsafe")
    binary_bytes = binary.read_bytes()
    elf_bytes = elf.read_bytes()
    _binary_elf_link(binary_bytes, elf_bytes)
    marker = (
        f"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE={profile}|"
        f"ROLE={role}|SHA256={descriptor}"
    ).encode("ascii")
    if binary_bytes.count(marker) != 1 or elf_bytes.count(marker) != 1:
        raise PackError(f"{environment} descriptor marker differs")
    return {
        "environment": environment,
        "binary": binary.as_posix(),
        "binary_bytes": len(binary_bytes),
        "binary_sha256": hashlib.sha256(binary_bytes).hexdigest(),
        "elf": elf.as_posix(),
        "elf_bytes": len(elf_bytes),
        "elf_sha256": hashlib.sha256(elf_bytes).hexdigest(),
        "descriptor_id": descriptor,
        "descriptor_marker": marker.decode("ascii"),
    }


def build_release() -> dict[str, Any]:
    candidates = []
    for values in _defines():
        index = int(values["index"])
        lower = values["PF_NAME_LOWER"]
        profile = values["PF_EXPECTED_PROFILE"]
        treatment_env = f"ec5_pfm_{lower}"
        recovery_env = f"{treatment_env}_white"
        treatment = _artifact(treatment_env, values["PF_TREAT_DESCRIPTOR"], profile, "RUNTIME")
        recovery = _artifact(recovery_env, values["PF_WHITE_DESCRIPTOR"], profile, "OTP_WHITE")
        treatment.update(
            {
                "build_tag": values["PF_TREAT_BUILD_TAG"],
                "test_id": values["PF_TREAT_TEST_ID"],
                "nvs_namespace": values["PF_TREAT_NVS_NAMESPACE"],
                "action_id": values["PF_TREAT_ACTION"],
                "role": "PURE_FIELD_UNIFORM_CODE_ATLAS",
            }
        )
        recovery.update(
            {
                "build_tag": f"MF1750_EC5_PURE_FIELD_{values['PF_NAME']}_WHITE_V1_2026-08-22",
                "test_id": "EC5-FACTORY-OTP-WHITE-RECOVERY-V1",
                "nvs_namespace": f"pfw{lower}",
                "action_id": values["PF_WHITE_ACTION"],
                "role": "FACTORY_OTP_WHITE_RECOVERY",
            }
        )
        candidates.append(
            {
                "index": index,
                "key": values["PF_NAME"],
                "payload_layout": "REF_R20_535__CS1_ACTIVE_CS2_COMMENTED__R21_FF704",
                "global_header": values["PF_GLOBAL_HEADER_PROFILE"],
                "profile_id": profile,
                "contract_id": values["PF_CONTRACT"],
                "release_id": hashlib.sha256(
                    (
                        "MF1750_STAGE3_REFERENCE_535_MATRIX_20260822|"
                        f"{values['PF_NAME']}|RELEASE|{values['PF_RELEASE_REVISION']}"
                    ).encode()
                ).hexdigest(),
                "treatment": treatment,
                "recovery": recovery,
            }
        )
    root = {
        "schema_version": 1,
        "kind": KIND,
        "campaign_id": "MF1750_STAGE3_REFERENCE_535_MATRIX_20260822",
        "candidate_order": [item["key"] for item in candidates],
        "candidate_count": 2,
        "treatment_refresh_count": 2,
        "white_recovery_refresh_count": 2,
        "maximum_planned_refresh_count": 4,
        "per_screen_controller_waveform_sets": 2,
        "per_controller_pixel_codes": 8,
        "per_screen_endpoint_observations": 16,
        "total_endpoint_observations": 32,
        "generated_include_sha256": _sha(GENERATED_INCLUDE),
        "reference_evidence": {
            "exact_chip_source": "User/EDP_init.c",
            "active_535_sha256": "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b",
            "commented_535_sha256": "2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26",
            "table_geometry": "7_HEADER_PLUS_6_CATEGORIES_X_8_GROUPS_X_11_BYTES",
            "record_splicing": False,
            "codes_8_through_15": False,
            "adjacent_public_structure_only": True,
            "adjacent_register_values_copied": False,
        },
        "frame_contract": {
            "width": 1024,
            "height": 600,
            "controller_width": 512,
            "region_width": 128,
            "region_height": 300,
            "borders": False,
            "spatial_dithering": False,
            "histogram": [76800] * 8,
            "frame_sha256": FRAME_SHA256,
            "frame_fnv1a": 0x52FA55C5,
            "cs1_dtm_sha256": CS1_SHA256,
            "cs1_dtm_fnv1a": 0x8935B9C5,
            "cs2_dtm_sha256": CS2_SHA256,
            "cs2_dtm_fnv1a": 0xD36139C5,
        },
        "fixed_safety_axes": {
            "spi_hz": 1_000_000,
            "partial_refresh": False,
            "window_commands": False,
            "unknown_commands": False,
            "raw_lut_ingress": False,
            "raw_frame_ingress": False,
            "vcom_write_or_sweep": False,
            "voltage_sweep": False,
            "mid_refresh_power_cut": False,
            "retry": False,
            "automatic_recovery": False,
            "automatic_chaining": False,
        },
        "source_bindings": {path.as_posix(): _sha(path) for path in SOURCE_FILES},
        "candidates": candidates,
    }
    return physical._seal(root)  # noqa: SLF001


def validate_release(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    physical._validate_seal(value, label="reference-535 release")  # noqa: SLF001
    rebuilt = build_release()
    if value != rebuilt:
        raise PackError("release content differs from current source/build artifacts")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    materialize = sub.add_parser("materialize")
    materialize.add_argument("--output", type=Path, required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--release", type=Path, required=True)
    sub.add_parser("describe")
    args = parser.parse_args(argv)
    try:
        value = validate_release(args.release) if args.command == "validate" else build_release()
        if args.command == "materialize":
            if args.output.exists():
                raise PackError("output already exists")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(contract.canonical_json_bytes(value) + b"\n")
    except (PackError, ValueError, OSError) as error:
        print(f"reference-535 pack error: {error}")
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
