from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any, Mapping

import pytest

from tools import mf1750_ec5_h3_c23_compiled_identity as compiled
from tools import mf1750_ec5_h3_c23_first_treatment_once as treatment_facade
from tools import mf1750_ec5_h3_c23_matched_control_contract as contract
from tools import mf1750_ec5_h3_c23_matched_control_physical_once as physical
from tools import mf1750_ec5_h3_c23_matched_control_release as release
from tools import mf1750_ec5_h3_c23_matched_pair_evidence as pair
from tools import mf1750_ec5_h3_c23_matched_trace_audit as trace


REPO_ROOT = Path(__file__).resolve().parents[1]
TREATMENT_RELEASE = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_EMPIRICAL_H3_RELEASES_20260812_V7"
    / "WF23_25-release.json"
)
CONTROL_BUILD = (
    REPO_ROOT
    / ".pio"
    / "build-h3-c23-matched-no-r20-r21-wf23-25"
    / "ec5_h3_c23_matched_no_r20_r21_wf23_25"
)
RECOVERY_BUILD = (
    REPO_ROOT
    / ".pio"
    / "build-h3-c23-matched-control-otp-white-wf23-25"
    / "ec5_h3_c23_matched_control_otp_white_wf23_25"
)
CONTROL_SOURCE = REPO_ROOT / "src" / "ec5_h3_c23_matched_control_main.cpp"
RECOVERY_SOURCE = REPO_ROOT / "src" / "ec5_h3_c23_matched_control_otp_white_main.cpp"


def _load_fake_engine() -> Any:
    name = "tests._mf1750_ec5_h3_c23_fake_device_engine"
    path = REPO_ROOT / "tests" / "test_mf1750_ec5_h3_matched_control_host.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("could not load the matched-control fake device")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    module.contract = contract
    module.compiled = compiled
    module.physical = physical
    module.release = release
    module.pair = pair
    return module


_fake_engine = _load_fake_engine()


class FakeC23Device(_fake_engine.FakeDevice):
    def _version(self) -> dict[str, Any]:
        value = super()._version()
        if self.ordinal == 1:
            value["profile"]["electrical_values_source"] = "matched_wf23_25_constants"
        return value


def _materialize_release() -> Mapping[str, Any]:
    return release.materialize_release(
        treatment_release_file=TREATMENT_RELEASE,
        control_elf=CONTROL_BUILD / "firmware.elf",
        control_binary=CONTROL_BUILD / "firmware.bin",
        control_source=CONTROL_SOURCE,
        recovery_elf=RECOVERY_BUILD / "firmware.elf",
        recovery_binary=RECOVERY_BUILD / "firmware.bin",
        recovery_source=RECOVERY_SOURCE,
    )


@pytest.fixture(scope="module")
def release_root() -> Mapping[str, Any]:
    return _materialize_release()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contract.canonical_json_bytes(value) + b"\n")


def test_trace_and_release_bind_exact_c23_t23_pair(
    release_root: Mapping[str, Any],
) -> None:
    summary = release.validate_release(release_root)
    audit = release_root["compiled_treatment_control_trace_audit"]
    assert summary["valid"] is True
    assert summary["profile_id"] == "WF23_25"
    assert summary["pinned_treatment_release_id"] == (
        "9ea2100e3934f95edd08a367d979c1eb340e5c67c316873806749a4a57de16f4"
    )
    assert summary["control_binary_sha256"] == (
        "44e7c55c45be3bdae8acf9b6c6d97f62d05c071786fa63fa460f8a7d32a54dfe"
    )
    assert summary["recovery_binary_sha256"] == (
        "8deba59ec437adf40414084e8f6d42d44fb74cd65b4ec45b3b87be6ffa8f6edb"
    )
    assert audit["kind"] == trace.KIND
    assert audit["classification"] == contract.CONTROL_DESIGN
    assert (
        audit["normalized_trace"]["strip_exact_four_upload_spans_equals_control"]
        is True
    )
    assert audit["compiled_common_functions"]["all_normalized_equal"] is True
    assert release_root["device_io_performed"] is False
    assert release_root["network_io_performed"] is False
    assert release_root["visible_refreshes"] == 0
    assert release_root["live_authorized"] is False


def test_c23_two_action_fake_chain_and_t23_preclaim_gate(
    tmp_path: Path, release_root: Mapping[str, Any]
) -> None:
    release_file = tmp_path / "C23-release.json"
    _write_json(release_file, release_root)
    context = physical.context_from_root(release_root)
    claims = tmp_path / "C23-claims"
    evidence: dict[int, tuple[Path, Path]] = {}

    for ordinal, screen in (
        (1, physical.SCREEN_INITIAL),
        (2, physical.SCREEN_RECOVERY),
    ):
        device = FakeC23Device(context, ordinal)
        diagnostic = physical.diagnose_j2_off(
            context,
            ordinal,
            operator_temperature_c="25.0",
            operator_screen_state=screen,
            operator_j2_state="OFF",
            operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
            requester=device,
        )
        diagnostic_file = tmp_path / f"C23-diagnostic-{ordinal}.json"
        _write_json(diagnostic_file, diagnostic)
        authorization = physical.offline_authorization(
            context,
            ordinal,
            selected_profile_id=contract.PROFILE_ID,
            operator_temperature_c="25.0",
            control_acceptance=contract.CONTROL_ACCEPTANCE_PHRASE,
            initial_precondition=(
                contract.INITIAL_PRECONDITION_PHRASE if ordinal == 1 else None
            ),
            operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
            diagnostic=diagnostic,
            claim_registry=claims,
        )
        assert authorization["authorization_token"].startswith(
            "AUTHORIZE_ONE_VISIBLE_EC5_H3_C23_MATCHED_"
        )
        result = physical.run_once(
            context,
            ordinal,
            operator_temperature_c="25.0",
            operator_j2_state="ON",
            operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
            authorization=authorization["authorization_token"],
            diagnostic=diagnostic,
            requester=device,
            claim_registry=claims,
            poll_count=1,
            poll_interval_seconds=0,
            sleeper=lambda _: None,
        )
        assert result["kind"] == physical.RESULT_KIND
        assert result["outcome"] == "success"
        assert result["visible_refreshes"] == 1
        assert result["automatic_chaining_performed"] is False
        result_file = tmp_path / f"C23-result-{ordinal}.json"
        _write_json(result_file, result)
        evidence[ordinal] = (diagnostic_file, result_file)

    leg = pair.finalize_control_leg(
        matched_release_file=release_file,
        control_diagnostic_file=evidence[1][0],
        control_result_file=evidence[1][1],
        recovery_diagnostic_file=evidence[2][0],
        recovery_result_file=evidence[2][1],
        control_observation=pair.CONTROL_OBSERVATION,
        recovery_observation=pair.CLEAN_WHITE_OBSERVATION,
        electrical_observation=pair.ELECTRICAL_OBSERVATION,
        balance_observation=pair.BALANCE_OBSERVATION,
        j2_off_observation=pair.J2_OFF_OBSERVATION,
        finalization_phrase=contract.CONTROL_RECOVERY_FINALIZATION_PHRASE,
    )
    leg_summary = pair.validate_control_leg(leg)
    assert leg_summary["valid"] is True
    assert leg_summary["control_temperature_c"] == "25.0"
    leg_file = tmp_path / "C23-control-leg.json"
    _write_json(leg_file, leg)

    gate = pair.treatment_preparation_gate(
        control_leg_file=leg_file,
        treatment_release_file=TREATMENT_RELEASE,
        operator_temperature_c="25.0",
    )
    gate_summary = pair.validate_treatment_gate(gate)
    assert gate_summary["valid"] is True
    assert gate_summary["treatment_release_id"] == (
        contract.PINNED_TREATMENT_RELEASE_ID
    )
    assert gate_summary["treatment_live_authorized"] is False
    gate_file = tmp_path / "C23-T23-gate.json"
    _write_json(gate_file, gate)

    facade = treatment_facade.validate_preclaim_gate(
        treatment_gate_file=gate_file,
        treatment_release_file=TREATMENT_RELEASE,
        operator_temperature_c="25.0",
    )
    assert facade["kind"] == treatment_facade.PRECLAIM_VALIDATION_KIND
    assert facade["pair_stage_order_completed"] == [1, 2]
    assert facade["next_pair_stage"] == 3
    assert facade["claim_created"] is False
    assert facade["network_requests"] == 0
    assert facade["visible_refreshes"] == 0
