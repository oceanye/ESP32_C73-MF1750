from __future__ import annotations

import copy
import json

import pytest

from host.runtime_waveform import contracts, execution_plan, format_registry
from tests.runtime_waveform_fixture import (
    build_complete_evidence_fixture,
    rebind_bundle_to_candidate,
    refresh_registration_artifact,
)


def _compile(fixture: dict) -> dict:
    return execution_plan.compile_execution_plan(
        fixture["candidate_manifest_bytes"],
        fixture["controller_payload_bytes"],
        evidence_bundle=fixture["bundle"],
        evidence_artifact_bytes=fixture["artifacts"],
        trusted_format_registrations=fixture["registry"],
    )


def test_reference_candidate_stays_blocked_without_a_registered_format_id() -> None:
    candidate = contracts.build_reference_blocked_candidate(
        created_at="2026-08-10T09:05:00+08:00"
    )
    result = execution_plan.compile_execution_plan(
        contracts.canonical_json_bytes(candidate), {}
    )
    assert result["compiled"] is False
    assert result["classification"] == format_registry.BLOCKED_FORMAT_NOT_REGISTERED
    assert result["steps"] == []
    assert result["execution_ready"] is False
    assert result["visible_refresh_authorized"] is False


def test_repeated_inputs_compile_to_identical_byte_free_plan() -> None:
    fixture = build_complete_evidence_fixture()
    first = _compile(fixture)
    second = _compile(fixture)
    assert first == second
    report = execution_plan.validate_execution_plan(
        first, trusted_format_registration=fixture["registration"]
    )
    assert report["valid"] is True
    assert report["step_count"] == 4
    assert first["integrity"]["canonical_sha256"] == report["canonical_sha256"]
    assert first["payload_bytes_embedded"] is False
    assert first["callbacks_present"] is False
    assert first["authorization_token_issued"] is False
    assert first["execution_ready"] is False
    serialized = contracts.canonical_json_bytes(first)
    assert fixture["controller_payload_bytes"]["CS1"] not in serialized
    assert fixture["controller_payload_bytes"]["CS2"] not in serialized


def test_manifest_must_be_exact_canonical_json() -> None:
    fixture = build_complete_evidence_fixture()
    pretty = json.dumps(fixture["candidate"], indent=2).encode("utf-8")
    with pytest.raises(execution_plan.ExecutionPlanError, match="exact canonical"):
        execution_plan.compile_execution_plan(
            pretty,
            fixture["controller_payload_bytes"],
            evidence_bundle=fixture["bundle"],
            evidence_artifact_bytes=fixture["artifacts"],
            trusted_format_registrations=fixture["registry"],
        )


def test_any_manifest_field_tamper_breaks_evidence_binding() -> None:
    fixture = build_complete_evidence_fixture()
    fixture["candidate"]["created_at"] = "2026-08-10T09:05:01+08:00"
    fixture["candidate_manifest_bytes"] = contracts.canonical_json_bytes(
        fixture["candidate"]
    )
    with pytest.raises(execution_plan.ExecutionPlanError, match="candidate identity"):
        _compile(fixture)


def test_cs1_cs2_swap_missing_segment_and_single_side_tamper_fail_closed() -> None:
    fixture = build_complete_evidence_fixture()
    payloads = fixture["controller_payload_bytes"]
    fixture["controller_payload_bytes"] = {
        "CS1": payloads["CS2"],
        "CS2": payloads["CS1"],
    }
    with pytest.raises(execution_plan.ExecutionPlanError, match="CS1 payload"):
        _compile(fixture)

    fixture = build_complete_evidence_fixture()
    del fixture["controller_payload_bytes"]["CS2"]
    with pytest.raises(execution_plan.ExecutionPlanError, match="exact CS1/CS2"):
        _compile(fixture)

    fixture = build_complete_evidence_fixture()
    fixture["controller_payload_bytes"]["CS2"] += b"tamper"
    with pytest.raises(execution_plan.ExecutionPlanError, match="CS2 payload"):
        _compile(fixture)


def test_unknown_format_returns_stable_block_instead_of_guessing() -> None:
    fixture = build_complete_evidence_fixture()
    fixture["candidate"]["payload"]["format_id"] = "unknown-format"
    rebind_bundle_to_candidate(fixture)
    result = execution_plan.compile_execution_plan(
        fixture["candidate_manifest_bytes"],
        fixture["controller_payload_bytes"],
        evidence_bundle=fixture["bundle"],
        evidence_artifact_bytes=fixture["artifacts"],
        trusted_format_registrations=fixture["registry"],
    )
    assert result["compiled"] is False
    assert result["blocker_codes"] == [
        format_registry.BLOCKED_FORMAT_NOT_REGISTERED
    ]


def test_unknown_opcode_and_sequence_change_are_rejected_before_plan_output() -> None:
    fixture = build_complete_evidence_fixture()
    fixture["registration"]["steps"][0]["opcode"] = 0xA5
    refresh_registration_artifact(fixture)
    with pytest.raises(execution_plan.ExecutionPlanError, match="allowlisted"):
        _compile(fixture)

    fixture = build_complete_evidence_fixture()
    fixture["registration"]["steps"][0]["controller_target"] = "CS2"
    fixture["registration"]["steps"][2]["controller_target"] = "CS1"
    refresh_registration_artifact(fixture)
    with pytest.raises(execution_plan.ExecutionPlanError, match="exact sequence"):
        _compile(fixture)


def test_plan_tamper_breaks_step_and_canonical_hashes() -> None:
    fixture = build_complete_evidence_fixture()
    plan = _compile(fixture)
    changed = copy.deepcopy(plan)
    changed["steps"][1]["parameter_length"] += 1
    with pytest.raises(execution_plan.ExecutionPlanError, match="identity differs"):
        execution_plan.validate_execution_plan(
            changed, trusted_format_registration=fixture["registration"]
        )

    changed = copy.deepcopy(plan)
    changed["visible_refresh_authorized"] = True
    with pytest.raises(execution_plan.ExecutionPlanError, match="must be false"):
        execution_plan.validate_execution_plan(
            changed, trusted_format_registration=fixture["registration"]
        )
