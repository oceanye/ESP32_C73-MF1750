#!/usr/bin/env python3
"""Fail-closed one-shot host runner for the two WF23 C23 actions.

The frozen matched-control runner is loaded into an isolated module instance
and rebound to the dedicated C23 contract/release.  C23 uses a separate claim
namespace, evidence kinds, exact authorization text, device identities, and
screen-state assertions.  No action is automatic and this module never
flashes firmware, switches profiles, retries, or chains T23.
"""

from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from typing import Any, Final, Mapping

from tools import mf1750_ec5_h3_c23_matched_control_contract as contract
from tools import mf1750_ec5_h3_c23_matched_control_release as release


REPO_ROOT: Final = Path(__file__).resolve().parents[1]


def _load_engine() -> Any:
    name = "tools._mf1750_ec5_h3_c23_matched_physical_engine"
    path = REPO_ROOT / "tools" / "mf1750_ec5_h3_matched_control_physical_once.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("could not load the frozen matched-control runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_engine = _load_engine()
SCHEMA_VERSION: Final = 2
DIAGNOSTIC_KIND: Final = "mf1750-ec5-h3-c23-matched-control-j2-off-diagnostic-v2"
CLAIM_KIND: Final = "mf1750-ec5-h3-c23-matched-control-permanent-host-claim-v2"
RESULT_KIND: Final = "mf1750-ec5-h3-c23-matched-control-physical-once-result-v2"
OFFLINE_AUTHORIZATION_KIND: Final = (
    "mf1750-ec5-h3-c23-matched-control-offline-authorization-token-v2"
)
OUTPUT_ATTEMPT_KIND: Final = "mf1750-ec5-h3-c23-matched-control-output-attempt-v2"
DEFAULT_CLAIM_REGISTRY: Final = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_ec5_h3_c23_matched_control_claims_v2"
)
SCREEN_INITIAL: Final = "clean_white_initial_c23_pair_not_treatment_finalized"
SCREEN_RECOVERY: Final = "post_c23_control_unrecovered"

_engine.contract = contract
_engine.release = release
_engine.DIAGNOSTIC_KIND = DIAGNOSTIC_KIND
_engine.CLAIM_KIND = CLAIM_KIND
_engine.RESULT_KIND = RESULT_KIND
_engine.OFFLINE_AUTHORIZATION_KIND = OFFLINE_AUTHORIZATION_KIND
_engine.OUTPUT_ATTEMPT_KIND = OUTPUT_ATTEMPT_KIND
_engine.DEFAULT_CLAIM_REGISTRY = DEFAULT_CLAIM_REGISTRY
_engine.SCREEN_INITIAL = SCREEN_INITIAL
_engine.SCREEN_RECOVERY = SCREEN_RECOVERY


class _VersionContextProxy:
    def __init__(self, context: Any) -> None:
        self._context = context
        self.root = context.root
        self.profile_id = context.profile_id
        self.release_id = context.release_id

    def action(self, ordinal: int) -> Mapping[str, Any]:
        action = deepcopy(dict(self._context.action(ordinal)))
        if ordinal == 1:
            action["temperature_policy"]["kind"] = (
                "initial_control_at_experimental_fixed_25_guard"
            )
        return action

    def binding(self, ordinal: int) -> Mapping[str, Any]:
        return self._context.binding(ordinal)


_base_expect_version = _engine._expect_version


def _expect_version(value: Mapping[str, Any], context: Any, ordinal: int) -> None:
    normalized = deepcopy(dict(value))
    if ordinal == 1:
        profile = normalized.get("profile")
        policy = context.action(ordinal).get("temperature_policy")
        if (
            not isinstance(profile, Mapping)
            or profile.get("electrical_values_source") != "matched_wf23_25_constants"
        ):
            raise _engine.MatchedControlPhysicalError(
                "device C23 electrical-value source differs"
            )
        if not isinstance(policy, Mapping) or policy.get("kind") != (
            "c23_initial_control_exact_25_guard"
        ):
            raise _engine.MatchedControlPhysicalError(
                "C23 exact-temperature policy differs"
            )
        normalized["profile"] = {
            **dict(profile),
            "electrical_values_source": "matched_wf20_25_constants",
        }
    _base_expect_version(normalized, _VersionContextProxy(context), ordinal)


_engine._expect_version = _expect_version
_base_required_authorization = _engine.required_authorization


def required_authorization(
    context: Any,
    ordinal: int,
    operator_temperature_c: str | float | int,
    diagnostic: Mapping[str, Any],
) -> str:
    token = _base_required_authorization(
        context, ordinal, operator_temperature_c, diagnostic
    )
    prefix = "AUTHORIZE_ONE_VISIBLE_EC5_H3_MATCHED_"
    if not token.startswith(prefix):
        raise _engine.MatchedControlPhysicalError(
            "C23 authorization base prefix differs"
        )
    return "AUTHORIZE_ONE_VISIBLE_EC5_H3_C23_MATCHED_" + token[len(prefix) :]


_engine.required_authorization = required_authorization
for _function_name in ("offline_authorization", "run_once"):
    _function = getattr(_engine, _function_name)
    if isinstance(_function.__kwdefaults__, dict) and "claim_registry" in (
        _function.__kwdefaults__
    ):
        _function.__kwdefaults__["claim_registry"] = DEFAULT_CLAIM_REGISTRY


MatchedControlPhysicalError = _engine.MatchedControlPhysicalError
MatchedControlPhysicalUnknown = _engine.MatchedControlPhysicalUnknown
HttpResponse = _engine.HttpResponse
ReleaseContext = _engine.ReleaseContext
atlas = _engine.atlas
context_from_root = _engine.context_from_root
load_release = _engine.load_release
describe = _engine.describe
diagnose_j2_off = _engine.diagnose_j2_off
validate_diagnostic = _engine.validate_diagnostic
offline_authorization = _engine.offline_authorization
run_once = _engine.run_once
main = _engine.main


def __getattr__(name: str) -> Any:
    return getattr(_engine, name)


if __name__ == "__main__":
    raise SystemExit(main())
