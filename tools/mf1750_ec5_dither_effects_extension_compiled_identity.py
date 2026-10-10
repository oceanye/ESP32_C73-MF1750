#!/usr/bin/env python3
"""Fail-closed offline ELF/BIN gate for the dither-effects extension.

The mature dither-atlas linked-object verifier is reused under a temporary,
process-local contract profile.  No serial, network, upload, or panel I/O is
available from this module.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Iterator, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_dither_color_atlas_compiled_identity as base  # noqa: E402
from tools import mf1750_ec5_dither_effects_extension_contract as contract  # noqa: E402


ACTION_RECORD = base.ACTION_RECORD
DRIVER_IDENTITY_RECORD = base.DRIVER_IDENTITY_RECORD

DRIVER_ROLES = (
    contract.ROLE_PAIR_GRADIENTS,
    contract.ROLE_EFFECTS_CHART,
    contract.ROLE_WHITE_AFTER_GRADIENTS,
)
DRIVER_ROLE_BY_ROLE = {
    contract.ROLE_PAIR_GRADIENTS: 0,
    contract.ROLE_WHITE_AFTER_GRADIENTS: 2,
    contract.ROLE_EFFECTS_CHART: 1,
    contract.ROLE_WHITE_AFTER_EFFECTS: 2,
}
DRIVER_SHA_SYMBOLS = {
    "pair_frame": base._local_object_symbol("DEE_PAIR_GRADIENTS_FRAME_SHA256"),
    "pair_cs1": base._local_object_symbol("DEE_PAIR_GRADIENTS_CS1_DTM_SHA256"),
    "pair_cs2": base._local_object_symbol("DEE_PAIR_GRADIENTS_CS2_DTM_SHA256"),
    "effects_frame": base._local_object_symbol("DEE_EFFECTS_CHART_FRAME_SHA256"),
    "effects_cs1": base._local_object_symbol("DEE_EFFECTS_CHART_CS1_DTM_SHA256"),
    "effects_cs2": base._local_object_symbol("DEE_EFFECTS_CHART_CS2_DTM_SHA256"),
    "white_frame": base._local_object_symbol("DEE_WHITE_FRAME_SHA256"),
    "white_dtm": base._local_object_symbol("DEE_WHITE_DTM_SHA256"),
}
ROLE_SHA_KEYS = {
    contract.ROLE_PAIR_GRADIENTS: ("pair_frame", "pair_cs1", "pair_cs2"),
    contract.ROLE_EFFECTS_CHART: (
        "effects_frame",
        "effects_cs1",
        "effects_cs2",
    ),
    contract.ROLE_WHITE_AFTER_GRADIENTS: (
        "white_frame",
        "white_dtm",
        "white_dtm",
    ),
}
EXPECTED_ENDPOINTS = (
    "/api/ec5/dither-effects-extension/version",
    "/api/ec5/dither-effects-extension/manifest",
    "/api/ec5/dither-effects-extension/status",
    "/api/ec5/dither-effects-extension/report",
    "/api/ec5/dither-effects-extension/arm",
    "/api/ec5/dither-effects-extension/execute",
)
FORBIDDEN_MARKERS = (
    b"ec5_dither_color_atlas_main.cpp",
    b"ec5_otp_transition_matrix_main.cpp",
    b"ec5_color_lab_main.cpp",
    b"ec5_color_lab_recovery_main.cpp",
    b"ec5_sixstate_main.cpp",
    b"ec5_u04_u05_compare_main.cpp",
    b"ec5_u07t_main.cpp",
    b"ec5_unknown_probe_main.cpp",
    b"/api/ec5/dither-color-atlas/",
    b"/api/ec5/otp-transition-matrix/",
    b"/api/ec5/color-lab/",
    b"/api/ec5/sixstate/",
    b"/api/frame\0",
    b"/api/diagnostic/frame-ingress\0",
    b"/api/lut",
    b"/api/waveform",
    b"/api/runtime-lut",
    b"/api/runtime-waveform",
    b"/api/ec5/retry",
    b"/api/ec5/recovery",
)


class DitherEffectsExtensionCompiledIdentityError(ValueError):
    """The selected extension ELF/BIN pair failed its exact identity gate."""


def _profile_contract() -> SimpleNamespace:
    return SimpleNamespace(
        CLASSIFICATION=contract.CLASSIFICATION,
        BUILD_TAG=contract.BUILD_TAG,
        TEST_ID=contract.TEST_ID,
        CAMPAIGN_ID=contract.CAMPAIGN_ID,
        DEVICE_API_VERSION=contract.DEVICE_API_VERSION,
        IDENTITY_REVISION=contract.IDENTITY_REVISION,
        LAYOUT_ID=contract.LAYOUT_ID,
        NVS_NAMESPACE=contract.NVS_NAMESPACE,
        NVS_KEY=contract.NVS_KEY,
        DESCRIPTORS=contract.DESCRIPTORS,
        ROLE_IDENTITIES=contract.ROLE_IDENTITIES,
        ROLES=DRIVER_ROLES,
        role_frame=contract.role_frame,
        campaign_manifest=contract.campaign_manifest,
    )


@contextmanager
def _configured_base() -> Iterator[None]:
    replacements = {
        "contract": _profile_contract(),
        "DRIVER_IDENTITIES_SYMBOL": base._local_object_symbol("DEE_IDENTITIES"),
        "DISPLAY_SYMBOL": (
            "_Z40epdDisplayCompiledDitherEffectsExtension"
            "29EpdDitherEffectsExtensionRole"
        ),
        "FIXTURE_VALIDATOR_SYMBOL": (
            "_Z49epdValidateCompiledDitherEffectsExtensionFixturesv"
        ),
        "EXPECTED_MAIN_FILE": "ec5_dither_effects_extension_main.cpp",
        "DRIVER_SHA_SYMBOLS": DRIVER_SHA_SYMBOLS,
        "ROLE_SHA_KEYS": ROLE_SHA_KEYS,
        "DRIVER_ROLE_BY_ROLE": DRIVER_ROLE_BY_ROLE,
        "EXPECTED_ENDPOINTS": EXPECTED_ENDPOINTS,
        "FORBIDDEN_MARKERS": FORBIDDEN_MARKERS,
    }
    original = {name: getattr(base, name) for name in replacements}
    base._histogram.cache_clear()
    try:
        for name, value in replacements.items():
            setattr(base, name, value)
        yield
    finally:
        for name, value in original.items():
            setattr(base, name, value)
        base._histogram.cache_clear()


def required_identity_strings() -> tuple[str, ...]:
    with _configured_base():
        return base.required_identity_strings()


def validate_artifacts(elf_file: Path, binary_file: Path) -> dict[str, Any]:
    """Deep-validate one exact extension ELF/BIN pair, offline only."""

    try:
        with _configured_base():
            report = base.validate_artifacts(elf_file, binary_file)
    except base.DitherColorAtlasCompiledIdentityError as error:
        raise DitherEffectsExtensionCompiledIdentityError(str(error)) from error
    report["kind"] = "mf1750-ec5-dither-effects-extension-compiled-identity-validation"
    report["driver"]["role_count"] = 3
    report["negative_identity_scan"]["forbidden_marker_count"] = len(FORBIDDEN_MARKERS)
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-artifacts", allow_abbrev=False)
    validate.add_argument("--elf", type=Path, required=True)
    validate.add_argument("--binary", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = validate_artifacts(args.elf, args.binary)
    except DitherEffectsExtensionCompiledIdentityError as error:
        print(f"EC5 dither-effects compiled-identity error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
