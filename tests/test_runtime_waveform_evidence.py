from __future__ import annotations

import copy

import pytest

from host.runtime_waveform import contracts, evidence, format_registry
from tests.runtime_waveform_fixture import (
    build_complete_evidence_fixture,
    rebind_bundle_to_candidate,
)


def _validate(fixture: dict) -> dict:
    return evidence.validate_evidence_bundle(
        fixture["candidate"],
        fixture["bundle"],
        controller_payload_bytes=fixture["controller_payload_bytes"],
        artifact_bytes=fixture["artifacts"],
        trusted_format_registrations=fixture["registry"],
    )


def test_production_format_registry_is_exactly_the_l535_geometry_and_read_only() -> None:
    # The first production registration (2026-10-09) covers the L535 535-byte
    # geometry; its review basis is the sealed PAL1 chain strict native audit.
    assert set(format_registry.REGISTERED_FORMATS) == {
        format_registry.L535_GEOMETRY_FORMAT_ID
    }
    registration = format_registry.trusted_registration_for(
        format_registry.L535_GEOMETRY_FORMAT_ID
    )
    assert registration is not None
    assert [step["opcode"] for step in registration["steps"]] == [0xE9, 0x20, 0xE9, 0x20]
    with pytest.raises(TypeError):
        format_registry.REGISTERED_FORMATS["unsafe"] = {}  # type: ignore[index]


def test_byte_backed_fixture_completes_only_the_offline_evidence_envelope() -> None:
    fixture = build_complete_evidence_fixture()
    report = _validate(fixture)
    assert report["offline_evidence_complete"] is True
    assert report["blocker_codes"] == []
    assert report["hardware_execution_eligible"] is False
    assert report["execution_ready"] is False
    assert report["visible_refresh_authorized"] is False
    assert report["hardware_io_performed"] is False

    evaluation = contracts.evaluate_candidate(
        fixture["candidate"],
        controller_payload_bytes=fixture["controller_payload_bytes"],
        evidence_bundle=fixture["bundle"],
        evidence_artifact_bytes=fixture["artifacts"],
        trusted_format_registrations=fixture["registry"],
    )
    assert evaluation["manifest_contract_complete"] is True
    assert evaluation["offline_contract_complete"] is True
    assert evaluation["deep_evidence_validated"] is True
    assert evaluation["hardware_execution_eligible"] is False
    assert evaluation["execution_ready"] is False


def test_candidate_fields_without_deep_evidence_are_not_offline_complete() -> None:
    fixture = build_complete_evidence_fixture()
    report = contracts.evaluate_candidate(
        fixture["candidate"],
        controller_payload_bytes=fixture["controller_payload_bytes"],
    )
    assert report["manifest_contract_complete"] is True
    assert report["offline_contract_complete"] is False
    assert report["deep_evidence_validated"] is False
    assert "deep_evidence_bundle_not_supplied" in report["offline_blocker_codes"]


def test_artifact_tampering_and_missing_segments_fail_closed() -> None:
    fixture = build_complete_evidence_fixture()
    fixture["artifacts"]["electrical_approval"] += b"tampered"
    with pytest.raises(evidence.EvidenceBundleError, match="byte identity differs"):
        _validate(fixture)

    fixture = build_complete_evidence_fixture()
    del fixture["artifacts"]["white_recovery_contract"]
    with pytest.raises(evidence.EvidenceBundleError, match="artifact byte roles differ"):
        _validate(fixture)


def test_payload_swap_and_single_controller_fail_closed() -> None:
    fixture = build_complete_evidence_fixture()
    payloads = fixture["controller_payload_bytes"]
    fixture["controller_payload_bytes"] = {
        "CS1": payloads["CS2"],
        "CS2": payloads["CS1"],
    }
    with pytest.raises(evidence.EvidenceBundleError, match="CS1 payload identity differs"):
        _validate(fixture)

    fixture = build_complete_evidence_fixture()
    fixture["controller_payload_bytes"] = {
        "CS1": fixture["controller_payload_bytes"]["CS1"]
    }
    with pytest.raises(evidence.EvidenceBundleError, match="exact CS1/CS2"):
        _validate(fixture)


@pytest.mark.parametrize(
    ("binding", "field", "replacement", "message"),
    [
        ("panel_binding", "batch_id", "wrong-batch", "panel/batch/controller"),
        (
            "panel_binding",
            "controller_revision",
            "wrong-revision",
            "panel/batch/controller",
        ),
        ("electrical_binding", "vcom_mv", -1.0, "electrical"),
        (
            "recovery_binding",
            "validated_on_sacrificial_panel",
            False,
            "recovery",
        ),
    ],
)
def test_exact_panel_electrical_and_recovery_bindings_are_enforced(
    binding: str, field: str, replacement: object, message: str
) -> None:
    fixture = build_complete_evidence_fixture()
    fixture["bundle"][binding][field] = replacement
    with pytest.raises(evidence.EvidenceBundleError, match=message):
        _validate(fixture)


def test_null_reviewer_cannot_be_rebound_into_deep_evidence() -> None:
    fixture = build_complete_evidence_fixture()
    fixture["candidate"]["provenance"]["vendor_or_panel_owner_review_id"] = None
    rebind_bundle_to_candidate(fixture)
    with pytest.raises(contracts.RuntimeWaveformContractError, match="reviewer"):
        contracts.evaluate_candidate(
            fixture["candidate"],
            controller_payload_bytes=fixture["controller_payload_bytes"],
            evidence_bundle=fixture["bundle"],
            evidence_artifact_bytes=fixture["artifacts"],
            trusted_format_registrations=fixture["registry"],
        )


def test_exact_sequence_rejects_order_change_and_disguised_opcode() -> None:
    fixture = build_complete_evidence_fixture()
    registration = copy.deepcopy(fixture["registration"])
    registration["steps"][0], registration["steps"][1] = (
        registration["steps"][1],
        registration["steps"][0],
    )
    with pytest.raises(format_registry.FormatRegistrationError, match="indexes"):
        format_registry.validate_format_registration(registration)

    registration = copy.deepcopy(fixture["registration"])
    registration["steps"][0]["opcode"] = 0xA5
    with pytest.raises(format_registry.FormatRegistrationError, match="allowlisted"):
        format_registry.validate_format_registration(registration)


def test_current_production_registry_keeps_even_complete_test_fields_blocked() -> None:
    fixture = build_complete_evidence_fixture()
    with pytest.raises(evidence.EvidenceBundleError, match="artifact record roles differ"):
        evidence.validate_evidence_bundle(
            fixture["candidate"],
            fixture["bundle"],
            controller_payload_bytes=fixture["controller_payload_bytes"],
            artifact_bytes=fixture["artifacts"],
        )
    assert (
        format_registry.trusted_registration_for(
            fixture["candidate"]["payload"]["format_id"]
        )
        is None
    )
