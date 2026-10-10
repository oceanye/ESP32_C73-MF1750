#!/usr/bin/env python3
"""Offline evidence/finalization gates for the C23-before-T23 pair."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any, Final

from tools import mf1750_ec5_h3_c23_matched_control_contract as contract
from tools import mf1750_ec5_h3_c23_matched_control_physical_once as control_physical
from tools import mf1750_ec5_h3_c23_matched_control_release as control_release


REPO_ROOT: Final = Path(__file__).resolve().parents[1]


def _load_engine() -> Any:
    name = "tools._mf1750_ec5_h3_c23_matched_pair_engine"
    path = REPO_ROOT / "tools" / "mf1750_ec5_h3_matched_pair_evidence.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("could not load the frozen matched-pair evidence engine")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_engine = _load_engine()
SCHEMA_VERSION: Final = 2
CONTROL_LEG_KIND: Final = "mf1750-ec5-h3-c23-control-leg-v2"
TREATMENT_GATE_KIND: Final = "mf1750-ec5-h3-c23-treatment-preparation-gate-v2"
PAIR_KIND: Final = "mf1750-ec5-h3-c23-t23-final-pair-evidence-v2"
PAIR_ORDER_ATTESTATION: Final = (
    "CONFIRM_C23_CONTROL_AND_WHITE_COMPLETED_BEFORE_T23_AND_WHITE__"
    "NO_AUTOMATIC_CHAINING"
)

_engine.contract = contract
_engine.control_physical = control_physical
_engine.control_release = control_release
_engine.CONTROL_LEG_KIND = CONTROL_LEG_KIND
_engine.TREATMENT_GATE_KIND = TREATMENT_GATE_KIND
_engine.PAIR_KIND = PAIR_KIND
_engine.PAIR_ORDER_ATTESTATION = PAIR_ORDER_ATTESTATION

MatchedPairEvidenceError = _engine.MatchedPairEvidenceError
CONTROL_OBSERVATION = _engine.CONTROL_OBSERVATION
TREATMENT_OBSERVATION = _engine.TREATMENT_OBSERVATION
CLEAN_WHITE_OBSERVATION = _engine.CLEAN_WHITE_OBSERVATION
ELECTRICAL_OBSERVATION = _engine.ELECTRICAL_OBSERVATION
BALANCE_OBSERVATION = _engine.BALANCE_OBSERVATION
J2_OFF_OBSERVATION = _engine.J2_OFF_OBSERVATION
PAIR_COMPARISONS = _engine.PAIR_COMPARISONS
finalize_control_leg = _engine.finalize_control_leg
validate_control_leg = _engine.validate_control_leg
load_control_leg = _engine.load_control_leg
treatment_preparation_gate = _engine.treatment_preparation_gate
materialize_treatment_gate = treatment_preparation_gate
validate_treatment_gate = _engine.validate_treatment_gate
load_treatment_gate = _engine.load_treatment_gate
finalize_pair = _engine.finalize_pair
validate_pair = _engine.validate_pair
write_new = _engine.write_new
write_new_json = write_new
main = _engine.main


def __getattr__(name: str) -> Any:
    return getattr(_engine, name)


if __name__ == "__main__":
    raise SystemExit(main())
