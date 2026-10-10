from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from tools import mf1750_ec5_h3_c_first_diagnostic_recovery_contract as recovery
from tools import mf1750_ec5_h3_matched_control_contract as contract


REPO_ROOT = Path(__file__).resolve().parents[1]
PRIOR_FAILURE = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_C_FIRST_LIVE_20260814_V10"
    / "c-j2-off-diagnostic.json"
)
V10_RELEASE = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260813_V10"
    / "WF20_25-release.json"
)


@pytest.fixture(scope="module")
def plan_bundle(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict, Path, Path]:
    root = tmp_path_factory.mktemp("h3-v10-diagnostic-recovery")
    diagnostic_output = root / "new-attempt" / "c-j2-off-diagnostic.json"
    plan = recovery.materialize_plan(
        prior_failure_file=PRIOR_FAILURE,
        release_file=V10_RELEASE,
        candidate_base_url="http://192.168.1.7",
        operator_reported_arp_mac="A4:CB:8F:D9:FC:D4",
        new_diagnostic_output=diagnostic_output,
    )
    return plan, diagnostic_output, root


def test_materialized_plan_binds_exact_failure_release_and_binary(
    plan_bundle: tuple[dict, Path, Path],
) -> None:
    plan, diagnostic_output, _ = plan_bundle

    assert plan["schema_version"] == 1
    assert plan["kind"] == recovery.KIND
    assert plan["classification"] == recovery.CLASSIFICATION
    prior = plan["prior_terminal_attempt"]
    assert prior["sha256"] == recovery.EXPECTED_PRIOR_FAILURE_FILE_SHA256
    assert prior["canonical_sha256"] == recovery.EXPECTED_PRIOR_FAILURE_CANONICAL_SHA256
    assert prior["state"] == "TERMINAL_PRECLAIM_FAILURE"
    assert prior["retry_allowed"] is False
    assert prior["prior_attempt_is_permanently_terminal"] is True
    assert prior["prior_attempt_must_not_be_retried"] is True
    release_record = plan["v10_release"]
    assert release_record["release_id"] == recovery.EXPECTED_RELEASE_ID
    assert release_record["sha256"] == recovery.EXPECTED_RELEASE_FILE_SHA256
    assert (
        release_record["canonical_sha256"] == recovery.EXPECTED_RELEASE_CANONICAL_SHA256
    )
    assert (
        release_record["control_artifact"]["binary"]["sha256"]
        == recovery.EXPECTED_CONTROL_BINARY_SHA256
    )
    assert (
        release_record["control_artifact"]["elf_sha256"]
        == recovery.EXPECTED_CONTROL_ELF_SHA256
    )
    assert plan["new_attempt"]["new_diagnostic_output"] == str(diagnostic_output)
    assert plan["new_attempt"]["relationship_to_prior_attempt"] == (
        "SEPARATE_NEW_ATTEMPT_NOT_RETRY"
    )


def test_candidate_arp_is_explicitly_non_authoritative_and_plan_bound(
    plan_bundle: tuple[dict, Path, Path],
) -> None:
    plan, _, _ = plan_bundle
    locator = plan["network_locator"]

    assert locator["candidate_base_url"] == "http://192.168.1.7"
    assert locator["expected_device_mac"] == recovery.EXPECTED_DEVICE_MAC
    assert locator["operator_reported_arp_mac"] == recovery.EXPECTED_DEVICE_MAC
    assert locator["observation_source"] == "unverified_operator_input"
    assert locator["arp_observation_captured_by_this_tool"] is False
    for key in (
        "arp_cache_is_device_identity_proof",
        "arp_cache_is_reachability_proof",
        "arp_cache_is_fresh_boot_binding_proof",
        "arp_cache_is_authorization",
    ):
        assert locator[key] is False
    assert locator["candidate_locator_status"] == (
        "UNPROVEN_REQUIRES_FRESH_CONFIRMATION"
    )
    assert locator["fresh_post_boot_ip_to_exact_mac_confirmation_required"] is True

    authority = plan["two_stage_future_authority"]
    assert authority["required"] is True
    assert authority["satisfied_by_plan"] is False
    assert authority["stage_order"] == ["NEW_BOOT", "READ_ONLY_DIAGNOSTIC"]
    assert authority["prior_authorization_reusable"] is False
    assert authority["copyable_authorization_token_emitted"] is False
    assert authority["new_boot_stage"]["authorized_by_plan"] is False
    assert authority["diagnostic_stage"]["authorized_by_plan"] is False
    assert authority["stage_a_new_boot_intent_sha256"] == contract.sha256(
        authority["new_boot_stage"]["intent"]
    )
    assert authority["stage_b_diagnostic_intent_template_sha256"] == (
        contract.sha256(authority["diagnostic_stage"]["intent_template"])
    )
    assert "AUTHORIZE" not in json.dumps(plan, sort_keys=True)


def test_boot_is_one_volatile_operation_not_zero_mutations(
    plan_bundle: tuple[dict, Path, Path],
) -> None:
    plan, _, _ = plan_bundle
    accounting = plan["boot_and_mutation_accounting"]
    boot_intent = plan["two_stage_future_authority"]["new_boot_stage"]["intent"]
    combined_intent = plan["two_stage_future_authority"][
        "combined_non_authorizing_plan_intent"
    ]

    assert accounting == {
        "new_boot_operations_exactly": 1,
        "new_boot_is_volatile_state_change": True,
        "new_boot_performed_by_plan_materialization": False,
        "persistent_flash_or_nvs_mutations": 0,
        "diagnostic_api_mutations": 0,
        "visible_refreshes": 0,
    }
    assert boot_intent["new_boot_operations_exactly"] == 1
    assert boot_intent["new_boot_is_volatile_state_change"] is True
    assert combined_intent["new_boot_operations_exactly"] == 1
    assert combined_intent["persistent_flash_or_nvs_mutations"] == 0
    assert combined_intent["diagnostic_api_mutations"] == 0
    assert plan["offline_materialization"]["device_mutations"] == 0
    assert plan["offline_materialization"]["reset_or_usb_action_performed"] is False


def test_diagnostic_budget_is_four_ordered_gets_and_nothing_mutating(
    plan_bundle: tuple[dict, Path, Path],
) -> None:
    plan, _, _ = plan_bundle
    budget = plan["read_only_diagnostic_budget"]
    base = "/api/ec5/h3-matched-control-v2"

    assert budget["ordered_requests"] == [
        {"ordinal": 1, "method": "GET", "path": f"{base}/version"},
        {"ordinal": 2, "method": "GET", "path": f"{base}/manifest"},
        {"ordinal": 3, "method": "GET", "path": f"{base}/status"},
        {"ordinal": 4, "method": "GET", "path": f"{base}/report"},
    ]
    assert budget["successful_diagnostic_exact_get_requests"] == 4
    assert budget["maximum_get_requests"] == 4
    assert budget["maximum_post_requests"] == 0
    assert budget["maximum_claims"] == 0
    assert budget["maximum_persistent_flash_or_nvs_mutations"] == 0
    assert budget["maximum_diagnostic_api_mutations"] == 0
    assert budget["maximum_visible_refreshes"] == 0
    assert budget["stop_on_first_error"] is True
    assert budget["no_retry"] is True
    assert budget["no_automatic_recovery"] is True
    assert budget["no_automatic_chaining"] is True


def test_deep_preexecution_validation_is_deterministic(
    plan_bundle: tuple[dict, Path, Path],
) -> None:
    plan, _, _ = plan_bundle
    summary = recovery.validate_plan(plan, require_new_output_absent=True)

    assert summary["valid"] is True
    assert summary["offline_plan_valid"] is True
    assert summary["execution_ready"] is False
    assert summary["canonical_sha256"] == plan["integrity"]["canonical_sha256"]
    assert summary["plan_id"] == plan["plan_id"]
    assert summary["validation_mode"] == "PRE_EXECUTION_OUTPUT_ABSENT"
    assert summary["new_output_absence_gate_required"] is True
    assert summary["new_boot_operations_exactly"] == 1
    assert summary["persistent_flash_or_nvs_mutation_budget"] == 0
    assert summary["diagnostic_api_mutation_budget"] == 0
    assert summary["copyable_authorization_token_emitted"] is False
    assert summary["unsatisfied_gates"] == [
        "sealed_new_boot_receipt",
        "fresh_onsite_gate",
        "trusted_single_ip_binding",
        "unique_execution_facade_and_attempt_reservation",
        "new_boot_user_authorization",
        "read_only_diagnostic_user_authorization",
    ]
    assert summary["live_authorized"] is False
    assert summary["device_io_performed"] is False


@pytest.mark.parametrize(
    "value",
    (
        "http://192.168.1.7/api",
        "http://192.168.1.7:80",
        "http://example.invalid",
        "https://192.168.1.7",
        "http://8.8.8.8",
    ),
)
def test_candidate_locator_rejects_non_bare_non_rfc1918_urls(value: str) -> None:
    with pytest.raises(recovery.DiagnosticRecoveryContractError):
        recovery._normalize_candidate_base_url(value)  # noqa: SLF001


def test_plan_output_cannot_consume_reserved_diagnostic_path(
    plan_bundle: tuple[dict, Path, Path],
) -> None:
    plan, diagnostic_output, _ = plan_bundle

    with pytest.raises(
        recovery.DiagnosticRecoveryContractError,
        match="plan output must differ",
    ):
        recovery.write_new_plan(diagnostic_output, plan)
    assert not diagnostic_output.exists()


def test_plan_output_rejects_immediate_symlink_parent(
    plan_bundle: tuple[dict, Path, Path],
) -> None:
    plan, _, root = plan_bundle
    real_parent = root / "real-plan-parent"
    link_parent = root / "linked-plan-parent"
    real_parent.mkdir()
    try:
        link_parent.symlink_to(real_parent, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks unavailable: {error}")

    with pytest.raises(
        recovery.DiagnosticRecoveryContractError,
        match="plan output parent chain contains a symlink",
    ):
        recovery.write_new_plan(link_parent / "plan.json", plan)
    assert not (real_parent / "plan.json").exists()


def test_reserved_output_rejects_immediate_symlink_parent(tmp_path: Path) -> None:
    real_parent = tmp_path / "real-diagnostic-parent"
    link_parent = tmp_path / "linked-diagnostic-parent"
    real_parent.mkdir()
    try:
        link_parent.symlink_to(real_parent, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks unavailable: {error}")

    with pytest.raises(
        recovery.DiagnosticRecoveryContractError,
        match="new diagnostic output parent chain contains a symlink",
    ):
        recovery._assert_new_output(  # noqa: SLF001
            link_parent / "diagnostic.json",
            prior_path=PRIOR_FAILURE.resolve(),
            release_path=V10_RELEASE.resolve(),
            require_absent=True,
        )


def test_plan_file_is_canonical_and_exclusive(
    plan_bundle: tuple[dict, Path, Path],
) -> None:
    plan, _, root = plan_bundle
    plan_file = root / "materialized" / "plan.json"
    recovery.write_new_plan(plan_file, plan)

    assert plan_file.read_bytes() == contract.canonical_json_bytes(plan) + b"\n"
    assert json.loads(plan_file.read_text(encoding="utf-8")) == plan
    with pytest.raises(
        recovery.DiagnosticRecoveryContractError,
        match="already exists",
    ):
        recovery.write_new_plan(plan_file, plan)


def test_structural_validation_survives_future_diagnostic_output(
    tmp_path: Path,
) -> None:
    diagnostic_output = tmp_path / "future" / "diagnostic.json"
    plan = recovery.materialize_plan(
        prior_failure_file=PRIOR_FAILURE,
        release_file=V10_RELEASE,
        candidate_base_url="http://192.168.1.7",
        operator_reported_arp_mac=recovery.EXPECTED_DEVICE_MAC,
        new_diagnostic_output=diagnostic_output,
    )
    diagnostic_output.parent.mkdir(parents=True)
    diagnostic_output.write_text("future terminal evidence\n", encoding="utf-8")

    summary = recovery.validate_plan(plan)
    assert summary["valid"] is True
    assert summary["validation_mode"] == "STRUCTURAL_POST_EXECUTION_COMPATIBLE"
    assert summary["new_output_absence_gate_required"] is False
    with pytest.raises(
        recovery.DiagnosticRecoveryContractError,
        match="already exists",
    ):
        recovery.validate_plan(plan, require_new_output_absent=True)


def test_resealed_semantic_tamper_fails_deep_reconstruction(
    plan_bundle: tuple[dict, Path, Path],
) -> None:
    plan, _, _ = plan_bundle
    # Deliberately preserve a valid outer seal; deterministic reconstruction
    # must still reject the changed non-authority assertion.
    tampered = deepcopy(plan)
    tampered["network_locator"]["arp_cache_is_device_identity_proof"] = True
    tampered = recovery._seal(  # noqa: SLF001
        {key: value for key, value in tampered.items() if key != "integrity"}
    )

    with pytest.raises(
        recovery.DiagnosticRecoveryContractError,
        match="deterministic deep reconstruction",
    ):
        recovery.validate_plan(tampered)
