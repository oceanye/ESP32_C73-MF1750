#!/usr/bin/env python3
"""Fail-closed feasibility audit for an SPD1657 3-bit LUT HOLD code.

This offline tool composes three identity-pinned local audits.  It emits only
metadata and a proof-obligation result; it never emits, mutates, or uploads a
waveform payload.  A repeated byte, an all-0xFF record, an optical endpoint,
or a cross-controller coincidence is not treated as electrical HOLD proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Final, Mapping

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_spd1657_phase_geometry_audit as geometry  # noqa: E402
from tools import mf1750_spd1657_record_semantics_audit as semantics  # noqa: E402
from tools import mf1750_spd1657_waveform_invariant_stats as invariants  # noqa: E402


KIND: Final = "mf1750-spd1657-hold-code-feasibility-audit"
SCHEMA_VERSION: Final = 1
DECISION: Final = "BLOCKED_NO_ELECTRICALLY_PROVEN_HOLD_CODE"

_EXPECTED_GEOMETRY_SHA256: Final = (
    "898a4e63edef212a36e8d4d8a2affdc9cc039412f9fb7244856ac6c4ac5fbb14"
)
_EXPECTED_INVARIANTS_SHA256: Final = (
    "eb2c391bcfcd1b5d5b6b0af39b84467353bfc1ce5a48abb2684e34c6df6e8978"
)
_EXPECTED_SEMANTICS_SHA256: Final = (
    "12954f599d9c76a8c0d87dbe3270e1b39e206aceb64dce740333fb3647350316"
)


class HoldFeasibilityError(RuntimeError):
    """Raised when an upstream evidence boundary or output invariant differs."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HoldFeasibilityError(message)


def _validate_sealed(
    value: Mapping[str, Any], *, expected_sha256: str, label: str
) -> None:
    integrity = value.get("integrity")
    _require(isinstance(integrity, Mapping), f"{label} integrity is missing")
    claimed = integrity.get("canonical_sha256")
    unsealed = {key: item for key, item in value.items() if key != "integrity"}
    observed = _sha256(_canonical(unsealed))
    _require(claimed == observed, f"{label} integrity does not verify")
    _require(observed == expected_sha256, f"{label} identity changed")


def _validate_geometry(value: Mapping[str, Any]) -> None:
    _require(
        value.get("kind") == "mf1750-spd1657-phase-geometry-audit"
        and value.get("schema_version") == 1,
        "phase-geometry audit identity changed",
    )
    _require(
        _sha256(_canonical(value)) == _EXPECTED_GEOMETRY_SHA256,
        "phase-geometry audit content changed",
    )
    boundary = value["semantic_boundary"]
    not_proven = boundary["not_proven"]
    required_negative_findings = (
        "group_is_a_chronological_phase_record",
        "any_byte_is_repeat_or_duration",
        "any_nibble_or_two_bit_projection_is_a_drive_level",
        "ff_means_disabled_end_skip_or_no_op",
        "zero_has_a_group_field_meaning",
        "category_index_maps_uniquely_to_a_pixel_code_or_color",
        "spd1656_field_semantics_apply_to_spd1657",
    )
    _require(
        all(not_proven.get(key) is True for key in required_negative_findings),
        "phase-geometry semantic boundary changed",
    )
    conditional = value["bounded_mode1_interpretation"]["conditional_mapping_only"]
    _require(
        conditional.get("then_all_ff_target_codes") == [4, 7]
        and conditional.get("direct_abi_or_loader_proof") is False,
        "conditional code mapping evidence changed",
    )


def _validate_invariants(value: Mapping[str, Any]) -> None:
    _require(
        value.get("kind") == "mf1750-spd1657-waveform-invariant-stats",
        "waveform-invariant audit identity changed",
    )
    _validate_sealed(
        value,
        expected_sha256=_EXPECTED_INVARIANTS_SHA256,
        label="waveform-invariant audit",
    )
    boundary = value["semantic_boundary"]
    _require(
        boundary.get("voltage_fields_assigned") is False
        and boundary.get("phase_or_duration_fields_assigned") is False
        and boundary.get("pixel_code_or_color_mapping_assigned") is False
        and boundary.get("runtime_payload_generated") is False
        and boundary.get("live_hardware_use_authorized") is False,
        "waveform-invariant semantic boundary changed",
    )
    _require(
        value["bounded_findings"].get("legacy_704_constants_are_not_identical") is True,
        "independent 704-byte R21 evidence changed",
    )


def _validate_semantics(value: Mapping[str, Any]) -> None:
    _require(
        value.get("kind") == "mf1750-spd1657-record-semantics-audit",
        "record-semantics audit identity changed",
    )
    _validate_sealed(
        value,
        expected_sha256=_EXPECTED_SEMANTICS_SHA256,
        label="record-semantics audit",
    )
    decision = value["adjudication"]
    required_false = (
        "legacy_GROUP_slot_proven_to_be_chronological_phase",
        "eleven_internal_byte_roles_proven",
        "record_repeat_or_duration_field_proven",
        "record_drive_state_or_polarity_field_proven",
        "record_voltage_level_field_proven",
        "all_ff_record_terminator_skip_or_noop_semantics_proven",
        "mode1_nine_category_mapping_proven",
        "DATA0_DATA1_category_or_controller_pairing_proven",
    )
    _require(
        all(decision.get(key) is False for key in required_false),
        "record-semantics proof boundary changed",
    )
    must_not = decision.get("must_not_use_for", [])
    _require(
        "generating a waveform payload or firmware include" in must_not,
        "record-semantics generation prohibition changed",
    )


def _proof_obligations() -> list[dict[str, Any]]:
    return [
        {
            "id": "exact_spd1657b_rev04_r20_r21_abi",
            "status": "MISSING",
            "required": (
                "authoritative field offsets, lengths, record ordering, R20/R21 "
                "composition, termination, padding, and mode selection"
            ),
        },
        {
            "id": "three_bit_code_to_lut_entry_mapping",
            "status": "MISSING",
            "required": (
                "code 0..7 mapping under the exact PSR/runtime mode for both "
                "controllers and both actually loaded tables"
            ),
        },
        {
            "id": "record_chronology_and_duration_decoder",
            "status": "MISSING",
            "required": (
                "ordered active phases, repeat counts, frame durations, loop rules, "
                "and inactive/terminator semantics"
            ),
        },
        {
            "id": "drive_symbol_voltage_decoder",
            "status": "MISSING",
            "required": (
                "every packed symbol to source and VCOM voltage, polarity, off, "
                "high-impedance, and level-selection semantics"
            ),
        },
        {
            "id": "all_ff_and_zero_semantics",
            "status": "MISSING",
            "required": (
                "direct proof whether 0xFF and 0x00 mean drive, no-op, padding, "
                "terminator, reserved, or another controller state"
            ),
        },
        {
            "id": "differential_zero_definition",
            "status": "MISSING",
            "required": (
                "vendor definition proving source-minus-VCOM equals zero for every "
                "active phase, including border and common-electrode behavior"
            ),
        },
        {
            "id": "charge_balance_definition_and_tolerance",
            "status": "MISSING",
            "required": (
                "signed voltage-time integration rule, amplitude and duration units, "
                "allowed residual, and repetition boundary"
            ),
        },
        {
            "id": "dual_controller_exact_profile_binding",
            "status": "MISSING",
            "required": (
                "identity-pinned proof of which R20/R21/header is active on CS1 and "
                "CS2 during the proposed HOLD operation"
            ),
        },
        {
            "id": "panel_fpl_safety_authority",
            "status": "MISSING",
            "required": (
                "panel/FPL-approved DC-balance, maximum dwell, recovery, temperature, "
                "and lifetime limits for the exact MF-17506 lot"
            ),
        },
    ]


def build_report() -> dict[str, Any]:
    """Build a metadata-only report; never materialize a waveform candidate."""

    geometry_report = geometry.build_report()
    invariant_report = invariants.build_report()
    semantics_report = semantics.build_report()
    _validate_geometry(geometry_report)
    _validate_invariants(invariant_report)
    _validate_semantics(semantics_report)

    geometry_profiles = geometry_report["profiles"]
    invariant_datasets = invariant_report["datasets"]
    conditional = geometry_report["bounded_mode1_interpretation"]
    obligations = _proof_obligations()

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": "offline_hold_code_feasibility_only",
        "decision": DECISION,
        "classification": "INSUFFICIENT_SEMANTIC_EVIDENCE_FAIL_CLOSED",
        "proof_target": {
            "pixel_code_domain": list(range(8)),
            "all_phase_zero": (
                "for every active phase, differential source-minus-VCOM drive is "
                "authoritatively decoded and exactly zero"
            ),
            "balanced_drive": (
                "the vendor-defined signed differential voltage-time integral is "
                "within the exact FPL tolerance over the complete repetition period"
            ),
            "either_target_sufficient_only_with_complete_exact_chip_proof": True,
        },
        "evidence_chain": {
            "phase_geometry": {
                "kind": geometry_report["kind"],
                "canonical_sha256": _EXPECTED_GEOMETRY_SHA256,
            },
            "waveform_invariants": {
                "kind": invariant_report["kind"],
                "canonical_sha256": invariant_report["integrity"]["canonical_sha256"],
            },
            "record_semantics": {
                "kind": semantics_report["kind"],
                "canonical_sha256": semantics_report["integrity"]["canonical_sha256"],
            },
        },
        "recovered_structure": {
            "WF20_25": {
                "r20_bytes": 799,
                "r20_sha256": (
                    "3cab2e2915205400bfdb0c2749a3e1e606cb6f190b8f3638849c532449a0ca26"
                ),
                "formula": "7_HEADER_PLUS_9_CATEGORIES_X_8_GROUPS_X_11_BYTES",
                "all_ff_group_count": geometry_profiles["WF20_25"]["body"][
                    "all_ff_group_count"
                ],
            },
            "WF23_25": {
                "r20_bytes": 799,
                "r20_sha256": (
                    "2eeae0e8e6a936cfd55e0a215371c114c037dbb70e701d8b95a2f560387788fb"
                ),
                "formula": "7_HEADER_PLUS_9_CATEGORIES_X_8_GROUPS_X_11_BYTES",
                "all_ff_group_count": geometry_profiles["WF23_25"]["body"][
                    "all_ff_group_count"
                ],
            },
            "L535_active": {
                "r20_transmitted_bytes": 535,
                "r20_sha256": invariant_datasets["legacy_wf_data_535"]["sha256"],
                "formula": "7_HEADER_PLUS_6_LABELED_CATEGORIES_X_8_GROUPS_X_11_BYTES",
                "vendor_category_labels": geometry_report["semantic_boundary"][
                    "proven"
                ]["legacy_category_labels"],
            },
            "L535_commented": {
                "r20_reference_bytes": 535,
                "r20_sha256": (
                    "2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26"
                ),
                "compiled_or_authorized_role": False,
            },
            "R21_704_evidence": {
                "armcc_all_ff_sha256": invariant_datasets["armcc_lut1_704"]["sha256"],
                "iar_nonidentical_sha256": invariant_datasets["legacy_iar_data1_704"][
                    "sha256"
                ],
                "two_704_constants_are_identical": False,
                "all_ff_means_zero_drive_proven": False,
            },
        },
        "conditional_only_not_a_candidate": {
            "assumption": conditional["conditional_mapping_only"]["assumption"],
            "codes_if_unproven_assumption_were_true": conditional[
                "conditional_mapping_only"
            ]["then_all_ff_target_codes"],
            "direct_abi_or_loader_proof": False,
            "all_ff_no_drive_semantics_proven": False,
            "permitted_use": "STRUCTURAL_CROSS_CONSISTENCY_ONLY",
            "candidate_generation_permitted": False,
        },
        "per_code_adjudication": [
            {
                "code": code,
                "lut_entry_mapping_proven": False,
                "all_phase_zero_proven": False,
                "balanced_drive_proven": False,
                "hold_code_qualified": False,
            }
            for code in range(8)
        ],
        "proof_obligations": obligations,
        "blocking_summary": {
            "missing_count": len(obligations),
            "all_required_fields_present": False,
            "optical_endpoint_color_is_electrical_hold_proof": False,
            "same_transport_code_before_and_after_is_hold_proof": False,
            "all_ff_record_is_hold_proof": False,
            "cross_generation_structure_is_exact_spd1657b_abi_proof": False,
        },
        "output_contract": {
            "hold_code": None,
            "candidate_generator_created": False,
            "candidate_payload_generated": False,
            "candidate_payload_bytes": 0,
            "firmware_include_generated": False,
            "live_runner_created": False,
            "eligible_for_live_use": False,
        },
        "safety": {
            "offline_only": True,
            "hardware_accessed": False,
            "relay_or_power_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "firmware_or_flash_written": False,
            "display_refresh_attempted": False,
            "raw_waveform_bytes_emitted": False,
            "runtime_payload_generated": False,
            "existing_firmware_modified": False,
            "vendor_evidence_modified": False,
        },
    }
    report["integrity"] = {
        "canonical_encoding": "UTF-8 sorted-key compact JSON excluding integrity",
        "canonical_sha256": _sha256(_canonical(report)),
    }
    return report


def write_new(path: Path, value: Mapping[str, Any]) -> None:
    """Write one create-only JSON audit, refusing aliases and overwrite."""

    path = Path(path)
    if path.suffix.lower() != ".json":
        raise HoldFeasibilityError("output must have a .json suffix")
    if path.is_symlink():
        raise HoldFeasibilityError("output must not be a symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    except FileExistsError as error:
        raise HoldFeasibilityError(f"refusing to overwrite {path}") from error


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = build_report()
        if args.output is not None:
            write_new(args.output, report)
    except (
        HoldFeasibilityError,
        geometry.PhaseGeometryAuditError,
        invariants.WaveformStatsError,
        semantics.RecordSemanticsAuditError,
        OSError,
    ) as error:
        print(f"hold-code feasibility error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=None if args.compact else 2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
