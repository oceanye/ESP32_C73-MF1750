#!/usr/bin/env python3
"""C23-first preclaim facade for the pinned WF23 T23 treatment action."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any, Final

from tools import mf1750_ec5_h3_c23_matched_control_contract as matched_contract
from tools import mf1750_ec5_h3_c23_matched_pair_evidence as pair_evidence


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PRECLAIM_VALIDATION_KIND: Final = "mf1750-ec5-h3-c23-first-t23-preclaim-validation-v1"


def _load_engine() -> Any:
    name = "tools._mf1750_ec5_h3_c23_first_treatment_engine"
    path = REPO_ROOT / "tools" / "mf1750_ec5_h3_c_first_treatment_once.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("could not load the frozen C-first treatment facade")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_engine = _load_engine()
_engine.matched_contract = matched_contract
_engine.pair_evidence = pair_evidence
_engine.PRECLAIM_VALIDATION_KIND = PRECLAIM_VALIDATION_KIND

CFirstTreatmentGateError = _engine.CFirstTreatmentGateError
TREATMENT_ORDINAL = _engine.TREATMENT_ORDINAL
validate_preclaim_gate = _engine.validate_preclaim_gate
main = _engine.main


def __getattr__(name: str) -> Any:
    return getattr(_engine, name)


if __name__ == "__main__":
    raise SystemExit(main())
