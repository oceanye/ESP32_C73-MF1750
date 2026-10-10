from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from tools import (
    mf1750_raw_p16_crossover_t4_v4_host_rejection_reconciliation_once as subject,
)


@pytest.fixture(scope="module")
def fixed_context():
    return subject._validate_local_authorities()  # noqa: SLF001


def test_fixed_chain_is_not_executed_and_binds_all_six_inputs(fixed_context):
    assert fixed_context["boot_nonce"] == "d0c12cfdbb56810a"
    assert set(fixed_context["bindings"]) == set(subject.FIXED_BINDINGS)
    assert len(fixed_context["bindings"]) == 6
    assert fixed_context["initial_status"]["arm_request_count"] == 0
    assert fixed_context["initial_status"]["execute_request_count"] == 0
    assert fixed_context["initial_status"]["total_driver_call_count"] == 0
    assert fixed_context["initial_report"]["terminal_state"] == "NOT_EXECUTED"
    assert fixed_context["initial_report"]["driver_called"] is False


def test_reconciliation_is_exactly_two_gets_o_excl_and_deep_validates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_context
):
    output = tmp_path / "reconciliation.json"
    calls: list[tuple[str, str]] = []

    def requester(base_url, path, *, method, headers, timeout):
        assert base_url == subject.FIXED_BASE_URL
        assert method == "GET"
        assert headers is None
        assert timeout == 3.0
        endpoint = path.rsplit("/", 1)[-1]
        calls.append((method, endpoint))
        response = (
            fixed_context["initial_status"]
            if endpoint == "status"
            else fixed_context["initial_report"]
        )
        return 200, deepcopy(response)

    monkeypatch.setattr(subject, "RECONCILIATION_OUTPUT", output.resolve())
    monkeypatch.setattr(
        subject, "_validate_local_authorities", lambda: fixed_context
    )
    value = subject.reconcile_host_rejection_once(
        confirm_j2_off=True,
        output=output,
        requester=requester,
        timeout=3.0,
    )
    assert calls == [("GET", "status"), ("GET", "report")]
    assert value["network"] == {"get": 2, "post": 0}
    assert value["terminal_state"] == "NOT_EXECUTED"
    assert value["campaign_id"] == subject.pack.CONFIG.campaign_id
    assert value["contract_id"] == subject.pack.build_report()["contract_id"]
    assert value["descriptor_id"] == fixed_context["action"]["descriptor_id"]
    assert value["action_id"] == fixed_context["action"]["action_id"]
    assert value["host_rejected_before_any_network_request"] is True
    assert value["network_requests"] == 0
    assert value["permanent_claims_created"] == 0
    assert value["arm_requests"] == 0
    assert value["execute_requests"] == 0
    assert value["driver_call_count_for_action"] == 0
    assert value["total_driver_call_count"] == 0
    assert value["visible_refreshes"] == 0
    assert value["same_boot"] is True
    assert value["w9_clean_white_remains_valid"] is True
    assert value["v4_action_must_not_be_retried"] is True
    assert value["safe_supersession"]["admissible"] is True
    assert value["safe_supersession"]["fresh_identity_required"] is True
    assert value["safe_supersession"]["v4_action_id_must_be_tombstoned"] is True
    validated, payload = subject.validate_reconciliation(output)
    assert validated["_validated_file_binding"]["bytes"] == len(payload)

    with pytest.raises(
        subject.T4V4HostRejectionReconciliationError,
        match="already exists",
    ):
        subject.reconcile_host_rejection_once(
            confirm_j2_off=True,
            output=output,
            requester=requester,
            timeout=3.0,
        )
    assert calls == [("GET", "status"), ("GET", "report")]


def test_missing_j2_off_confirmation_rejects_before_local_or_network(
    monkeypatch: pytest.MonkeyPatch,
):
    touched = False

    def forbidden():
        nonlocal touched
        touched = True
        raise AssertionError("local validation must not start")

    monkeypatch.setattr(subject, "_validate_local_authorities", forbidden)
    with pytest.raises(
        subject.T4V4HostRejectionReconciliationError,
        match="explicit J2-OFF",
    ):
        subject.reconcile_host_rejection_once(confirm_j2_off=False)
    assert touched is False


def test_same_boot_drift_fails_closed_and_seals_no_post_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_context
):
    output = tmp_path / "boot-drift-failure.json"

    def requester(_base_url, path, *, method, headers, timeout):
        assert method == "GET"
        endpoint = path.rsplit("/", 1)[-1]
        response = deepcopy(
            fixed_context["initial_status"]
            if endpoint == "status"
            else fixed_context["initial_report"]
        )
        response["boot_nonce"] = "ffffffffffffffff"
        if endpoint == "status":
            response["persisted_campaign_boot_nonce"] = "ffffffffffffffff"
        return 200, response

    monkeypatch.setattr(subject, "RECONCILIATION_OUTPUT", output.resolve())
    monkeypatch.setattr(
        subject, "_validate_local_authorities", lambda: fixed_context
    )
    with pytest.raises(
        subject.T4V4HostRejectionReconciliationError,
        match="failed and was sealed",
    ):
        subject.reconcile_host_rejection_once(
            confirm_j2_off=True,
            output=output,
            requester=requester,
        )
    failure = json.loads(output.read_bytes())
    assert failure["outcome"] == "reconciliation_failed_closed_read_only"
    assert failure["network"] == {"get": 2, "post": 0}
    assert failure["mutation_requests_sent"] == 0
    assert failure["safe_supersession"] == {"admissible": False}


def test_fixed_binding_tamper_is_rejected(monkeypatch: pytest.MonkeyPatch):
    changed = deepcopy(subject.FIXED_BINDINGS["j2_off_diagnostic"])
    changed["file_sha256"] = "0" * 64
    monkeypatch.setitem(subject.FIXED_BINDINGS, "j2_off_diagnostic", changed)
    with pytest.raises(
        subject.T4V4HostRejectionReconciliationError,
        match="file SHA differs",
    ):
        subject._load_bound("j2_off_diagnostic")  # noqa: SLF001
