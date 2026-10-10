"""Tests for the L535 geometry format registration and table builder."""

from __future__ import annotations

import unittest

from host.runtime_waveform import (
    contracts,
    execution_plan,
    format_registry,
    l535_table_builder as builder,
)


FORMAT_ID = builder.FORMAT_ID
ACTIVE_PREFIX_SHA = "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b"
ACTIVE_TABLE_SHA = ACTIVE_PREFIX_SHA  # transmitted table == the 535-byte prefix


class FormatRegistrationTests(unittest.TestCase):
    def test_registration_validates_and_is_trusted(self) -> None:
        registration = format_registry.trusted_registration_for(FORMAT_ID)
        self.assertIsNotNone(registration)
        assert registration is not None
        self.assertEqual(registration["format_id"], FORMAT_ID)
        self.assertEqual(
            [step["opcode"] for step in registration["steps"]],
            [0xE9, 0x20, 0xE9, 0x20],
        )
        self.assertEqual(
            [step["controller_target"] for step in registration["steps"]],
            ["CS1", "CS1", "CS2", "CS2"],
        )
        for step in registration["steps"]:
            if step["opcode"] == 0x20:
                self.assertEqual(step["parameter_length"], 535)

    def test_registration_sha_is_stable(self) -> None:
        registration = format_registry.trusted_registration_for(FORMAT_ID)
        assert registration is not None
        sha_a = format_registry.registration_sha256(registration)
        sha_b = format_registry.registration_sha256(registration)
        self.assertEqual(sha_a, sha_b)

    def test_format_document_identity_matches_registration(self) -> None:
        registration = format_registry.trusted_registration_for(FORMAT_ID)
        assert registration is not None
        self.assertEqual(
            builder.format_document_sha256(), registration["format_document_sha256"]
        )


class ReferenceFidelityTests(unittest.TestCase):
    def test_active_reference_matches_pinned_prefix(self) -> None:
        table = builder.from_reference("active")
        self.assertEqual(table.sha256, ACTIVE_TABLE_SHA)
        self.assertEqual(len(table.to_bytes()), 535)
        self.assertEqual(len(table.groups), 6)
        self.assertTrue(all(len(group) == 8 for group in table.groups))
        self.assertTrue(
            all(len(record) == 11 for group in table.groups for record in group)
        )

    def test_default_build_is_byte_identical_to_reference(self) -> None:
        reference = builder.from_reference("active")
        rebuilt = builder.build_table()
        self.assertEqual(rebuilt.to_bytes(), reference.to_bytes())
        self.assertEqual(rebuilt.sha256, ACTIVE_TABLE_SHA)

    def test_commented_reference_loads_with_distinct_header(self) -> None:
        active = builder.from_reference("active")
        commented = builder.from_reference("commented")
        self.assertNotEqual(active.header, commented.header)
        self.assertEqual(commented.header, bytes([0x00, 0x24, 0x78, 0x27, 0x20, 0x14, 0x03]))
        self.assertEqual(
            commented.knobs,
            {
                "vsh_lv_mv": 6600,
                "vsl_lv_mv": -15000,
                "vsh_lv2_mv": 6900,
                "vsl_lv2_mv": -6200,
                "gate_mv": 20000,
                "pll_code": 3,
            },
        )

    def test_unknown_role_rejected(self) -> None:
        with self.assertRaises(builder.L535TableError):
            builder.from_reference("mid")


class KnobTests(unittest.TestCase):
    def test_knob_round_trip(self) -> None:
        knobs = {
            "vsh_lv_mv": 6600,
            "vsl_lv_mv": -8400,
            "vsh_lv2_mv": 6900,
            "vsl_lv2_mv": -6200,
            "gate_mv": 20000,
            "pll_code": 3,
        }
        header = builder.header_bytes_from_knobs(knobs)
        self.assertEqual(builder.knobs_from_header_bytes(header), knobs)

    def test_knobbed_build_changes_only_header(self) -> None:
        reference = builder.from_reference("active")
        knobbed = builder.build_table({"vsh_lv_mv": 6600, "pll_code": 3})
        self.assertEqual(knobbed.groups, reference.groups)
        self.assertEqual(knobbed.header, bytes([0x00, 0x24, 0x78, 0x20, 0x1E, 0x14, 0x03]))
        self.assertNotEqual(knobbed.sha256, reference.sha256)
        # exactly two byte positions change (header index 1 and 6)
        diffs = [
            index
            for index, (a, b) in enumerate(
                zip(reference.to_bytes(), knobbed.to_bytes())
            )
            if a != b
        ]
        self.assertEqual(diffs, [1, 6])

    def test_invalid_knobs_rejected(self) -> None:
        with self.assertRaises(builder.L535TableError):
            builder.header_bytes_from_knobs(
                {
                    "vsh_lv_mv": 6050,  # not a 100 mV step
                    "vsl_lv_mv": -15000,
                    "vsh_lv2_mv": 6200,
                    "vsl_lv2_mv": -6000,
                    "gate_mv": 20000,
                    "pll_code": 2,
                }
            )
        with self.assertRaises(builder.L535TableError):
            builder.header_bytes_from_knobs(
                {
                    "vsh_lv_mv": 6000,
                    "vsl_lv_mv": -15000,
                    "vsh_lv2_mv": 6200,
                    "vsl_lv2_mv": -6000,
                    "gate_mv": 0,
                    "pll_code": 2,
                }
            )
        with self.assertRaises(builder.L535TableError):
            builder.build_table({"unknown_knob": 1})

    def test_table_structure_validation(self) -> None:
        with self.assertRaises(builder.L535TableError):
            builder.validate_table_bytes(b"\x00" * 534)
        with self.assertRaises(builder.L535TableError):
            builder.validate_table_bytes(b"\x01" + b"\x00" * 534)


class CandidateContractTests(unittest.TestCase):
    CREATED_AT = "2026-10-09T00:00:00+00:00"

    def _candidate(self) -> dict:
        table = builder.from_reference("active")
        return builder.to_candidate_manifest(table, created_at=self.CREATED_AT)

    def test_candidate_validates_and_only_attestable_gates_true(self) -> None:
        candidate = self._candidate()
        validated = contracts.validate_candidate(candidate)
        gates = validated["gates"]
        for name in contracts.GATE_NAMES:
            self.assertEqual(gates[name], name in builder.ATTESTABLE_GATES, name)

    def test_evaluation_is_blocked_with_open_obligations(self) -> None:
        candidate = self._candidate()
        table = builder.from_reference("active")
        evaluation = contracts.evaluate_candidate(
            candidate,
            controller_payload_bytes={"CS1": table.to_bytes(), "CS2": table.to_bytes()},
        )
        self.assertEqual(
            evaluation["classification"], "OFFLINE_ONLY_NOT_EXECUTABLE"
        )
        self.assertFalse(evaluation["hardware_execution_eligible"])
        self.assertFalse(evaluation["execution_ready"])
        self.assertTrue(
            evaluation["controller_payload_checks"]["CS1"]["identity_passed"]
        )
        self.assertTrue(
            evaluation["controller_payload_checks"]["CS2"]["identity_passed"]
        )
        blockers = set(evaluation["offline_blocker_codes"])
        for expected in (
            "controller_revision_identity_missing",
            "electrical_profile_incomplete",
            "phase_timing_undocumented",
            "known_good_profile_missing",
            "recovery_contract_missing",
            "otp_mode_restore_not_proven",
            "sacrificial_panel_recovery_not_validated",
            "deep_evidence_bundle_not_supplied",
            "gate_false:code_semantics_reviewed",
            "gate_false:electrical_parameters_approved",
            "gate_false:temperature_bin_approved",
            "gate_false:known_good_otp_equivalence_passed",
            "gate_false:independent_recovery_validated",
            "gate_false:sacrificial_panel_authorized",
            "gate_false:power_telemetry_and_hard_cutoff_ready",
            "gate_false:controller_revision_exact",
            "gate_false:portable_loader_source_reviewed",
        ):
            self.assertIn(expected, blockers)
        # attested gates must not show up as blockers
        for attested in builder.ATTESTABLE_GATES:
            self.assertNotIn(f"gate_false:{attested}", blockers)

    def test_manifest_canonical_bytes_load_into_plan_compiler(self) -> None:
        candidate = self._candidate()
        manifest = builder.canonical_manifest_bytes(candidate)
        loaded = execution_plan.load_canonical_manifest_bytes(manifest)
        self.assertEqual(loaded["payload"]["format_id"], FORMAT_ID)

    def test_plan_compilation_still_requires_p0_evidence(self) -> None:
        candidate = self._candidate()
        manifest = builder.canonical_manifest_bytes(candidate)
        table = builder.from_reference("active")
        with self.assertRaisesRegex(
            execution_plan.ExecutionPlanError, "complete P0 evidence bundle"
        ):
            execution_plan.compile_execution_plan(
                manifest,
                {"CS1": table.to_bytes(), "CS2": table.to_bytes()},
            )

    def test_knob_changes_are_auditable_in_manifest(self) -> None:
        reference = builder.from_reference("active")
        knobbed = builder.build_table({"vsh_lv_mv": 6600})
        candidate_a = builder.to_candidate_manifest(
            reference, created_at=self.CREATED_AT, profile_id="audit-a"
        )
        candidate_b = builder.to_candidate_manifest(
            knobbed, created_at=self.CREATED_AT, profile_id="audit-b"
        )
        sha_a = contracts.sha256_hex(contracts.canonical_json_bytes(candidate_a))
        sha_b = contracts.sha256_hex(contracts.canonical_json_bytes(candidate_b))
        self.assertNotEqual(sha_a, sha_b)
        payload_a = candidate_a["payload"]["controller_payloads"][0]["sha256"]
        payload_b = candidate_b["payload"]["controller_payloads"][0]["sha256"]
        self.assertNotEqual(payload_a, payload_b)
        self.assertEqual(payload_a, reference.sha256)
        self.assertEqual(payload_b, knobbed.sha256)


if __name__ == "__main__":
    unittest.main()
