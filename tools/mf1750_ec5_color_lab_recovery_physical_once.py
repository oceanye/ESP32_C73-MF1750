#!/usr/bin/env python3
"""One-shot physical runner for the frozen EC5 COLOR_LAB recovery release.

This adapter reuses the audited one-shot transport/state engine while binding
it, under a process-local lock, to the recovery campaign, response kinds,
NVS identity, and a separate permanent-claim registry.  Every entry point
replays the exact V3 release and the sealed V2 incident/claim boundary before
performing any request or creating any claim.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sys
from typing import Any, Iterator, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_color_lab_contract as superseded_contract  # noqa: E402
from tools import mf1750_ec5_color_lab_physical_once as engine  # noqa: E402
from tools import mf1750_ec5_color_lab_recovery_campaign as campaign  # noqa: E402
from tools import mf1750_ec5_color_lab_recovery_contract as contract  # noqa: E402


DEVICE_KIND_PREFIX = "mf1750-ec5-color-lab-recovery"
CLAIM_KIND = f"{DEVICE_KIND_PREFIX}-permanent-host-claim"
RESULT_KIND = f"{DEVICE_KIND_PREFIX}-physical-once-result"
OBSERVATION_KIND = f"{DEVICE_KIND_PREFIX}-manual-observation"
J2_OFF_DIAGNOSTIC_KIND = f"{DEVICE_KIND_PREFIX}-j2-off-diagnostic"
RECONCILIATION_KIND = f"{DEVICE_KIND_PREFIX}-late-terminal-readback-reconciliation"
OBSERVATION_TEMPLATE_KIND = f"{DEVICE_KIND_PREFIX}-observation-template"
CLAIM_REGISTRY_ID = "workspace-mf1750-ec5-color-lab-recovery-claims-v1"
DEFAULT_CLAIM_REGISTRY = (
    REPO_ROOT / ".test-output" / "hardware" / ".mf1750_ec5_color_lab_recovery_claims"
)

EXPECTED_RELEASE_FILE_SHA256 = (
    "301b6677630798161ad7a6915dbc2046cc10eb6584ea27abfa23228c4299d69d"
)
EXPECTED_RELEASE_CANONICAL_SHA256 = (
    "93a7f1e617909d7fad9ff1dbff59b9e83d3951d9c6519084da1da22536cf1d4a"
)
EXPECTED_BUNDLE_FILE_SHA256 = (
    "94aa9aa23fbd23bf37dda142f7e7ba5a6f69c5db309adcdd8707dfac8bd32dcc"
)
EXPECTED_BUNDLE_CANONICAL_SHA256 = (
    "ffda1caa8c362f9adcdabc60ba2a41f1c2a310daf4c225a2d01f84301571aa0c"
)
EXPECTED_INCIDENT_RESULT_SHA256 = (
    "9bf2a770f0d802864f7bedda7fdd79f710097ec03a70aa58bff7558dd1c99726"
)
EXPECTED_INCIDENT_RESULT_INTEGRITY = (
    "e4ab7d8ee055b4adb2493213130990c9d8b9fa6bf5d560259ffca6cb79ca7e6a"
)
EXPECTED_INCIDENT_CLAIM_SHA256 = (
    "b565fe7ea65b9bebdefec8620ef9996f0fc5e1d4334a18510c9154e6ad672bba"
)
EXPECTED_INCIDENT_CLAIM_INTEGRITY = (
    "3b33024ab518e06faa2040c3a18da8c1b510a49526212ed050a632aac94889bb"
)

ColorLabRecoveryPhysicalError = engine.ColorLabPhysicalError
ReleaseContext = engine.ReleaseContext
Preflight = engine.Preflight
Requester = engine.Requester
http_request = engine.http_request

_ENGINE_LOCK = engine._ENGINE_BINDING_LOCK
_ENGINE_BINDINGS: Mapping[str, Any] = {
    "campaign": campaign,
    "contract": contract,
    "DEVICE_KIND_PREFIX": DEVICE_KIND_PREFIX,
    "CLAIM_KIND": CLAIM_KIND,
    "RESULT_KIND": RESULT_KIND,
    "OBSERVATION_KIND": OBSERVATION_KIND,
    "J2_OFF_DIAGNOSTIC_KIND": J2_OFF_DIAGNOSTIC_KIND,
    "RECONCILIATION_KIND": RECONCILIATION_KIND,
    "OBSERVATION_TEMPLATE_KIND": OBSERVATION_TEMPLATE_KIND,
    "CLAIM_REGISTRY_ID": CLAIM_REGISTRY_ID,
    "DEFAULT_CLAIM_REGISTRY": DEFAULT_CLAIM_REGISTRY,
}


@contextmanager
def _bound_engine() -> Iterator[None]:
    """Temporarily bind the shared engine and restore every global in finally."""

    with _ENGINE_LOCK:
        previous = {name: getattr(engine, name) for name in _ENGINE_BINDINGS}
        for name, value in _ENGINE_BINDINGS.items():
            setattr(engine, name, value)
        try:
            yield
        finally:
            for name, value in previous.items():
                setattr(engine, name, value)


def _exact_recovery_gate(context: ReleaseContext) -> None:
    """Replay the exact V3 release and its immutable V2 incident boundary."""

    try:
        checked = campaign.validate_materialized_release(context.release_file)
    except campaign.ColorLabCampaignError as error:
        raise ColorLabRecoveryPhysicalError(
            f"recovery release validation failed: {error}"
        ) from error
    if (
        checked.get("file_sha256") != EXPECTED_RELEASE_FILE_SHA256
        or checked.get("canonical_sha256") != EXPECTED_RELEASE_CANONICAL_SHA256
        or checked.get("execution_eligible") is not True
        or context.release_file_sha256 != EXPECTED_RELEASE_FILE_SHA256
        or context.release_canonical_sha256 != EXPECTED_RELEASE_CANONICAL_SHA256
        or context.release_root.get("kind") != campaign.RELEASE_KIND
        or context.release_root.get("execution_eligible") is not True
    ):
        raise ColorLabRecoveryPhysicalError("exact V3 recovery release differs")

    boundary = context.release_root.get("recovery_boundary")
    if not isinstance(boundary, Mapping):
        raise ColorLabRecoveryPhysicalError("V3 recovery incident boundary is absent")
    incident = boundary.get("incident_result")
    old_claim = boundary.get("permanent_claim")
    old_release = boundary.get("superseded_release")
    if (
        not isinstance(incident, Mapping)
        or incident.get("file_sha256") != EXPECTED_INCIDENT_RESULT_SHA256
        or incident.get("integrity_sha256") != EXPECTED_INCIDENT_RESULT_INTEGRITY
        or incident.get("outcome") != "unknown_do_not_retry_or_recover"
        or not isinstance(old_claim, Mapping)
        or old_claim.get("file_sha256") != EXPECTED_INCIDENT_CLAIM_SHA256
        or old_claim.get("integrity_sha256") != EXPECTED_INCIDENT_CLAIM_INTEGRITY
        or old_claim.get("state") != "permanently_claimed_before_first_arm_post"
        or not isinstance(old_release, Mapping)
        or old_release.get("file_sha256")
        != campaign.SUPERSEDED_COLOR_LAB_RELEASE_FILE_SHA256
        or old_release.get("canonical_sha256")
        != campaign.SUPERSEDED_COLOR_LAB_RELEASE_CANONICAL_SHA256
        or boundary.get("old_action_id") != campaign.SUPERSEDED_COLOR_LAB_ACTION_1_ID
        or boundary.get("old_authorization_remains_consumed") is not True
        or boundary.get("old_claim_must_not_be_removed_or_reused") is not True
        or boundary.get("old_fault_state_ignored_not_cleared") is not True
        or boundary.get("global_nvs_clear") is not False
        or boundary.get("new_nvs_namespace") != contract.NVS_NAMESPACE
        or boundary.get("new_nvs_key") != contract.NVS_KEY
    ):
        raise ColorLabRecoveryPhysicalError("exact V2 incident/claim binding differs")

    new_ids = {str(item["action_id"]) for item in context.actions}
    old_ids = {
        str(item["hardware_action_id"]) for item in superseded_contract.DESCRIPTORS
    }
    if (
        len(new_ids) != campaign.ACTION_COUNT
        or new_ids & old_ids
        or contract.NVS_NAMESPACE == superseded_contract.NVS_NAMESPACE
        or contract.NVS_KEY == superseded_contract.NVS_KEY
        or DEFAULT_CLAIM_REGISTRY
        == REPO_ROOT / ".test-output/hardware/.mf1750_ec5_color_lab_claims"
    ):
        raise ColorLabRecoveryPhysicalError("recovery identity isolation differs")


def validate_bundle(bundle_manifest_file: Path) -> dict[str, Any]:
    try:
        checked = campaign.validate_bundle(bundle_manifest_file)
    except campaign.ColorLabCampaignError as error:
        raise ColorLabRecoveryPhysicalError(
            f"recovery bundle validation failed: {error}"
        ) from error
    if (
        checked.get("file_sha256") != EXPECTED_BUNDLE_FILE_SHA256
        or checked.get("canonical_sha256") != EXPECTED_BUNDLE_CANONICAL_SHA256
        or checked.get("release_file_sha256") != EXPECTED_RELEASE_FILE_SHA256
        or checked.get("execution_eligible") is not True
        or checked.get("visible_refresh_authorized_by_bundle") != 0
    ):
        raise ColorLabRecoveryPhysicalError("exact V3 recovery bundle differs")
    context = load_release(Path(str(checked["execution_authority"])))
    return {
        **checked,
        "physical_runner_exact_release_gate": True,
        "action_count": len(context.actions),
    }


def load_release(release_file: Path) -> ReleaseContext:
    with _bound_engine():
        context = engine.load_release(release_file)
    _exact_recovery_gate(context)
    return context


def required_authorization(context: ReleaseContext, ordinal: int) -> str:
    _exact_recovery_gate(context)
    with _bound_engine():
        return engine.required_authorization(context, ordinal)


def describe(context: ReleaseContext, ordinal: int) -> dict[str, Any]:
    _exact_recovery_gate(context)
    with _bound_engine():
        result = engine.describe(context, ordinal)
    return {
        **result,
        "exact_recovery_incident_gate": True,
        "claim_registry": str(DEFAULT_CLAIM_REGISTRY),
    }


def observation_template(context: ReleaseContext, ordinal: int) -> dict[str, Any]:
    _exact_recovery_gate(context)
    with _bound_engine():
        return engine.observation_template(context, ordinal)


def preflight(
    context: ReleaseContext, base_url: str, ordinal: int, **kwargs: Any
) -> Preflight:
    _exact_recovery_gate(context)
    with _bound_engine():
        return engine.preflight(context, base_url, ordinal, **kwargs)


def diagnose_j2_off(
    context: ReleaseContext,
    base_url: str,
    *,
    evidence_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    **kwargs: Any,
) -> dict[str, Any]:
    _exact_recovery_gate(context)
    with _bound_engine():
        return engine.diagnose_j2_off(
            context,
            base_url,
            evidence_file=evidence_file,
            claim_registry=claim_registry,
            **kwargs,
        )


def validate_j2_off_diagnostic(
    context: ReleaseContext,
    evidence_file: Path,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    _exact_recovery_gate(context)
    with _bound_engine():
        return engine.validate_j2_off_diagnostic(
            context, evidence_file, claim_registry=claim_registry
        )


def run_once(
    context: ReleaseContext,
    base_url: str,
    ordinal: int,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    **kwargs: Any,
) -> dict[str, Any]:
    _exact_recovery_gate(context)
    with _bound_engine():
        return engine.run_once(
            context,
            base_url,
            ordinal,
            claim_registry=claim_registry,
            **kwargs,
        )


def validate_result(
    context: ReleaseContext,
    result_file: Path,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    _exact_recovery_gate(context)
    with _bound_engine():
        return engine.validate_result(
            context, result_file, claim_registry=claim_registry
        )


def reconcile_result(
    context: ReleaseContext,
    base_url: str,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    **kwargs: Any,
) -> dict[str, Any]:
    _exact_recovery_gate(context)
    with _bound_engine():
        return engine.reconcile_result(
            context,
            base_url,
            claim_registry=claim_registry,
            **kwargs,
        )


def validate_reconciliation(
    context: ReleaseContext,
    reconciliation_file: Path,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    _exact_recovery_gate(context)
    with _bound_engine():
        return engine.validate_reconciliation(
            context,
            reconciliation_file,
            claim_registry=claim_registry,
        )


def finalize_observation(
    context: ReleaseContext,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    **kwargs: Any,
) -> dict[str, Any]:
    _exact_recovery_gate(context)
    with _bound_engine():
        return engine.seal_observation(context, claim_registry=claim_registry, **kwargs)


seal_observation = finalize_observation


def validate_observation(
    context: ReleaseContext,
    observation_file: Path,
    *,
    result_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    _exact_recovery_gate(context)
    with _bound_engine():
        return engine.validate_observation(
            context,
            observation_file,
            result_file=result_file,
            claim_registry=claim_registry,
        )


def _engine_main(argv: Sequence[str] | None) -> int:
    with _bound_engine():
        original_load = engine.load_release

        def exact_load(path: Path) -> ReleaseContext:
            context = original_load(path)
            _exact_recovery_gate(context)
            return context

        engine.load_release = exact_load
        try:
            return engine.main(argv)
        finally:
            engine.load_release = original_load


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "validate-bundle":
        parser = argparse.ArgumentParser(allow_abbrev=False)
        parser.add_argument("command", choices=("validate-bundle",))
        parser.add_argument("--bundle", type=Path, required=True)
        args = parser.parse_args(arguments)
        try:
            output = validate_bundle(args.bundle)
        except ColorLabRecoveryPhysicalError as error:
            print(f"EC5 COLOR_LAB recovery error: {error}", file=sys.stderr)
            return 2
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        return 0
    return _engine_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
