#!/usr/bin/env python3
"""Offline compiled-trace audit for the WF23 C23/T23 matched pair.

The implementation reuses the frozen WF20 trace engine in an isolated module
instance, but replaces every profile, payload, symbol, build-manifest, and
compiled-identity binding with the dedicated WF23/C23 values.  It performs no
device, serial, network, upload, flash, or visible-display I/O.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Final, Mapping, Sequence

from tools import mf1750_ec5_h3_c23_compiled_identity as compiled
from tools import mf1750_ec5_h3_c23_matched_control_contract as contract


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
SCHEMA_VERSION: Final = 1
KIND: Final = "mf1750-ec5-h3-c23-matched-compiled-trace-audit"


def _load_engine() -> Any:
    name = "tools._mf1750_ec5_h3_c23_matched_trace_engine"
    path = REPO_ROOT / "tools" / "mf1750_ec5_h3_matched_trace_audit.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("could not load the frozen matched-trace engine")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_engine = _load_engine()
MatchedTraceAuditError = _engine.MatchedTraceAuditError


class _CompiledIdentityAdapter:
    validate_image = staticmethod(compiled.validate_image)
    MatchedControlCompiledIdentityError = compiled.C23CompiledIdentityError


_engine.control_compiled = _CompiledIdentityAdapter
_engine.control_contract = contract
_engine.PROFILE_ID = contract.PROFILE_ID
_engine.KIND = KIND
_engine.TREATMENT_CONFIG = REPO_ROOT / "platformio.runtime_lut_wf23_25.ini"
_engine.CONTROL_CONFIG = REPO_ROOT / "platformio.h3_c23_matched_control_wf23_25.ini"
_engine.CONTROL_DISPLAY = (
    "epdDisplayCompiledH3C23MatchedControl(EpdH3C23MatchedControlRole)"
)
_engine.CONTROL_WRITE = (
    "(anonymous namespace)::h3c23WriteFixedPayload((anonymous namespace)::"
    "H3C23FixedCommand, unsigned char const*, unsigned int)"
)
_engine.TREATMENT_PAYLOAD_SYMBOLS = {
    **_engine.TREATMENT_PAYLOAD_SYMBOLS,
    "power": "mf1750::runtime_lut::wf23_25_empirical_h3::kPowerPayload",
    "pll": "mf1750::runtime_lut::wf23_25_empirical_h3::kPllPayload",
    "r20": "mf1750::runtime_lut::wf23_25_empirical_h3::kR20Payload",
    "r21": "mf1750::runtime_lut::wf23_25_empirical_h3::kR21Payload",
}
_engine.CONTROL_PAYLOAD_SYMBOLS = {
    "runtime_psr": "(anonymous namespace)::H3C23_RUNTIME_PSR",
    "power": "(anonymous namespace)::H3C23_POWER_PAYLOAD",
    "pll": "(anonymous namespace)::H3C23_PLL_PAYLOAD",
    "tres": "(anonymous namespace)::H3C23_CONTROLLER_TRES",
    "e9": "(anonymous namespace)::H3C23_HIDDEN_ENABLE",
}
_engine.EXPECTED_SMALL_PAYLOADS = {
    "runtime_psr": bytes.fromhex("5fe9"),
    "power": bytes.fromhex("0f002a363444"),
    "pll": bytes.fromhex("02"),
    "tres": bytes.fromhex("02000258"),
    "e9": bytes.fromhex("01"),
}
_profile = contract.profile_row()
_engine.EXPECTED_R20_SHA256 = _profile["reference_r20_sha256"]
_engine.EXPECTED_R21_SHA256 = _profile["reference_r21_sha256"]
_engine_calls = _engine._calls


def _c23_calls(records: Sequence[Mapping[str, Any]], token: str) -> list[int]:
    if token == "h3mcWriteFixedPayload":
        token = "h3c23WriteFixedPayload"
    return _engine_calls(records, token)


_engine._calls = _c23_calls


def validate_seal(root: Mapping[str, Any]) -> str:
    return str(_engine.validate_seal(root))


def audit_pair(
    *,
    treatment_release_file: Path,
    control_elf_file: Path,
    control_binary_file: Path,
    control_transaction_source_file: Path,
    nm_tool: Path | None = None,
    objdump_tool: Path | None = None,
) -> dict[str, Any]:
    """Deep-audit the exact WF23 T23 and C23 compiled images offline."""

    raw = _engine.audit_pair(
        treatment_release_file=treatment_release_file,
        control_elf_file=control_elf_file,
        control_binary_file=control_binary_file,
        control_transaction_source_file=control_transaction_source_file,
        nm_tool=nm_tool,
        objdump_tool=objdump_tool,
    )
    unsigned = deepcopy(
        {
            key: value
            for key, value in raw.items()
            if key not in {"audit_id", "integrity"}
        }
    )
    unsigned["kind"] = KIND
    unsigned["classification"] = contract.CONTROL_DESIGN
    unsigned["causal_scope"]["T_not_equal_C_classification"] = (
        "DETECTABLE_INCREMENTAL_EFFECT_COMPATIBLE_WITH_R20_R21_CONTRIBUTION_"
        "NOT_ACCEPTANCE_OR_ABI_PROOF"
    )
    result = _engine._seal(unsigned)
    validate_seal(result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--treatment-release", type=Path, required=True)
    parser.add_argument("--control-elf", type=Path, required=True)
    parser.add_argument("--control-binary", type=Path, required=True)
    parser.add_argument("--control-transaction-source", type=Path, required=True)
    parser.add_argument("--nm", type=Path)
    parser.add_argument("--objdump", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = audit_pair(
            treatment_release_file=args.treatment_release,
            control_elf_file=args.control_elf,
            control_binary_file=args.control_binary,
            control_transaction_source_file=args.control_transaction_source,
            nm_tool=args.nm,
            objdump_tool=args.objdump,
        )
    except MatchedTraceAuditError as error:
        print(f"C23 matched-trace audit error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            indent=None if args.compact else 2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
