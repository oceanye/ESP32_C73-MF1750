from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from tools import mf1750_spd1657_hold_code_feasibility as hold


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report() -> dict[str, object]:
    return hold.build_report()


def test_all_eight_codes_fail_closed(report: dict[str, object]) -> None:
    assert report["decision"] == "BLOCKED_NO_ELECTRICALLY_PROVEN_HOLD_CODE"
    assert report["classification"] == ("INSUFFICIENT_SEMANTIC_EVIDENCE_FAIL_CLOSED")
    per_code = report["per_code_adjudication"]
    assert [item["code"] for item in per_code] == list(range(8))
    for item in per_code:
        assert item == {
            "code": item["code"],
            "lut_entry_mapping_proven": False,
            "all_phase_zero_proven": False,
            "balanced_drive_proven": False,
            "hold_code_qualified": False,
        }
    assert report["output_contract"]["hold_code"] is None


def test_recovered_r20_r21_l535_identities_are_exact(
    report: dict[str, object],
) -> None:
    recovered = report["recovered_structure"]
    assert recovered["WF20_25"] == {
        "r20_bytes": 799,
        "r20_sha256": (
            "3cab2e2915205400bfdb0c2749a3e1e606cb6f190b8f3638849c532449a0ca26"
        ),
        "formula": "7_HEADER_PLUS_9_CATEGORIES_X_8_GROUPS_X_11_BYTES",
        "all_ff_group_count": 34,
    }
    assert recovered["WF23_25"] == {
        "r20_bytes": 799,
        "r20_sha256": (
            "2eeae0e8e6a936cfd55e0a215371c114c037dbb70e701d8b95a2f560387788fb"
        ),
        "formula": "7_HEADER_PLUS_9_CATEGORIES_X_8_GROUPS_X_11_BYTES",
        "all_ff_group_count": 22,
    }
    assert recovered["L535_active"] == {
        "r20_transmitted_bytes": 535,
        "r20_sha256": (
            "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b"
        ),
        "formula": ("7_HEADER_PLUS_6_LABELED_CATEGORIES_X_8_GROUPS_X_11_BYTES"),
        "vendor_category_labels": [
            "VCOM",
            "Black",
            "White",
            "Yellow",
            "Red",
            "Power",
        ],
    }
    assert recovered["L535_commented"]["compiled_or_authorized_role"] is False
    r21 = recovered["R21_704_evidence"]
    assert r21["armcc_all_ff_sha256"] == (
        "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f"
    )
    assert r21["iar_nonidentical_sha256"] == (
        "6dbd5a232419da637084683867933a7f60ce06d28a5034136d0f0efae3015e6a"
    )
    assert r21["two_704_constants_are_identical"] is False
    assert r21["all_ff_means_zero_drive_proven"] is False


def test_structural_code_4_and_7_hint_is_not_promoted(
    report: dict[str, object],
) -> None:
    conditional = report["conditional_only_not_a_candidate"]
    assert conditional["codes_if_unproven_assumption_were_true"] == [4, 7]
    assert conditional["direct_abi_or_loader_proof"] is False
    assert conditional["all_ff_no_drive_semantics_proven"] is False
    assert conditional["candidate_generation_permitted"] is False
    for code in (4, 7):
        assert report["per_code_adjudication"][code]["hold_code_qualified"] is False


def test_every_required_electrical_field_remains_missing(
    report: dict[str, object],
) -> None:
    obligations = report["proof_obligations"]
    assert [item["id"] for item in obligations] == [
        "exact_spd1657b_rev04_r20_r21_abi",
        "three_bit_code_to_lut_entry_mapping",
        "record_chronology_and_duration_decoder",
        "drive_symbol_voltage_decoder",
        "all_ff_and_zero_semantics",
        "differential_zero_definition",
        "charge_balance_definition_and_tolerance",
        "dual_controller_exact_profile_binding",
        "panel_fpl_safety_authority",
    ]
    assert all(item["status"] == "MISSING" for item in obligations)
    assert report["blocking_summary"]["missing_count"] == len(obligations) == 9
    assert report["blocking_summary"]["all_required_fields_present"] is False


def test_output_contract_contains_no_candidate_payload_or_live_path(
    report: dict[str, object],
) -> None:
    assert report["output_contract"] == {
        "hold_code": None,
        "candidate_generator_created": False,
        "candidate_payload_generated": False,
        "candidate_payload_bytes": 0,
        "firmware_include_generated": False,
        "live_runner_created": False,
        "eligible_for_live_use": False,
    }
    safety = report["safety"]
    assert safety["offline_only"] is True
    assert all(safety[key] is False for key in safety if key != "offline_only")


def test_integrity_covers_complete_metadata_report(report: dict[str, object]) -> None:
    unsealed = {key: value for key, value in report.items() if key != "integrity"}
    assert (
        hashlib.sha256(hold._canonical(unsealed)).hexdigest()
        == report[  # noqa: SLF001
            "integrity"
        ]["canonical_sha256"]
    )
    assert report["evidence_chain"] == {
        "phase_geometry": {
            "kind": "mf1750-spd1657-phase-geometry-audit",
            "canonical_sha256": (
                "898a4e63edef212a36e8d4d8a2affdc9cc039412f9fb7244856ac6c4ac5fbb14"
            ),
        },
        "waveform_invariants": {
            "kind": "mf1750-spd1657-waveform-invariant-stats",
            "canonical_sha256": (
                "eb2c391bcfcd1b5d5b6b0af39b84467353bfc1ce5a48abb2684e34c6df6e8978"
            ),
        },
        "record_semantics": {
            "kind": "mf1750-spd1657-record-semantics-audit",
            "canonical_sha256": (
                "12954f599d9c76a8c0d87dbe3270e1b39e206aceb64dce740333fb3647350316"
            ),
        },
    }


def test_upstream_semantic_change_is_rejected_before_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    changed = deepcopy(hold.geometry.build_report())
    changed["semantic_boundary"]["not_proven"][
        "ff_means_disabled_end_skip_or_no_op"
    ] = False
    monkeypatch.setattr(hold.geometry, "build_report", lambda: changed)
    with pytest.raises(hold.HoldFeasibilityError, match="content changed"):
        hold.build_report()


def test_upstream_integrity_change_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    changed = deepcopy(hold.invariants.build_report())
    changed["semantic_boundary"]["phase_or_duration_fields_assigned"] = True
    monkeypatch.setattr(hold.invariants, "build_report", lambda: changed)
    with pytest.raises(hold.HoldFeasibilityError, match="integrity does not verify"):
        hold.build_report()


def test_create_only_json_audit_refuses_overwrite(
    tmp_path: Path, report: dict[str, object]
) -> None:
    output = tmp_path / "hold-feasibility.json"
    hold.write_new(output, report)
    observed = json.loads(output.read_text("utf-8"))
    assert observed == report
    with pytest.raises(hold.HoldFeasibilityError, match="refusing to overwrite"):
        hold.write_new(output, report)


def test_tool_source_has_no_transport_or_firmware_materializer() -> None:
    source = (ROOT / "tools" / "mf1750_spd1657_hold_code_feasibility.py").read_text(
        "utf-8"
    )
    for forbidden in (
        "urllib.request",
        "requests.",
        "serial.Serial",
        "subprocess",
        "platformio",
        "esptool",
        "kR20Payload[",
        "render_include(",
        "write_flash",
    ):
        assert forbidden not in source
