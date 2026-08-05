from __future__ import annotations

import json
import hashlib
import math
from pathlib import Path
import unittest

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # pragma: no cover - optional local contract audit dependency
    Draft202012Validator = None
    FormatChecker = None

from host.extended_color import (
    ExtendedColorRecordError,
    build_artifact,
    validate_electrical_record,
    validate_event_recovery_record,
    validate_optical_record,
    validate_run_record,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
WHEN = "2026-08-05T21:00:00+08:00"
LATER = "2026-08-05T21:01:00+08:00"
GENERATED = "2026-08-05T21:02:00+08:00"


def authorization(enabled: bool) -> dict[str, object]:
    return {
        "authorized": enabled,
        "authorization_id": "AUTH-001" if enabled else None,
        "recorded_at": WHEN if enabled else None,
    }


def run_record(hardware: bool) -> dict[str, object]:
    auth = {
        key: authorization(hardware and key != "flash_com8")
        for key in (
            "flash_com8",
            "power_off_confirmed",
            "power_on",
            "power_normal_confirmed",
            "send_frame",
            "post_refresh_confirmed",
            "final_power_off_tp1_confirmed",
        )
    }
    identity = build_artifact("transition-target", 1).identity.to_dict()
    if hardware:
        scope_payload = {
            "frame_sha256": identity["frame_sha256"],
            "test_id": "EC5-D-001",
        }
        authorization_scope = {
            **scope_payload,
            "canonical_sha256": hashlib.sha256(
                json.dumps(
                    scope_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest(),
        }
    else:
        authorization_scope = {
            "test_id": None,
            "frame_sha256": None,
            "canonical_sha256": None,
        }
    return {
        "schema_version": 2,
        "kind": "mf1750-extended-color-run",
        "test_id": "EC5-D-001",
        "run_id": "RUN-001",
        "stage": "D",
        "status": "completed" if hardware else "planned",
        "evidence_status": "complete" if hardware else "not_run",
        "null_reason": None if hardware else "hardware work not authorized",
        "hardware_tested": hardware,
        "generated_at": GENERATED if hardware else None,
        "asset_manifest_sha256": SHA_A if hardware else None,
        "panel": {
            "model": "MF-17506-M009F-T",
            "serial": "PANEL-001" if hardware else None,
            "pcb_revision": "MF1750 Rev A1",
            "controller": "SPD1657B",
            "controller_revision": "0x04",
            "r15": "removed",
            "r16_ohm": 0,
        },
        "authorization": auth,
        "authorization_scope": authorization_scope,
        "firmware": {
            "git_commit": "d" * 40 if hardware else None,
            "build_tag": "extended-color-test",
            "binary_sha256": SHA_B if hardware else None,
            "release_unknown_code_disabled": True,
        },
        "frame_identity": identity,
        "environment": {
            "temperature_c": 25.0 if hardware else None,
            "relative_humidity_percent": 50.0 if hardware else None,
            "record_ref": "environment/RUN-001.json" if hardware else None,
        },
        "started_at": WHEN if hardware else None,
        "finished_at": LATER if hardware else None,
    }


def optical_record(hardware: bool) -> dict[str, object]:
    return {
        "schema_version": 2,
        "kind": "mf1750-extended-color-optical",
        "run_id": "RUN-001",
        "hardware_tested": hardware,
        "evidence_status": "complete" if hardware else "not_run",
        "null_reason": None if hardware else "optical acquisition not run",
        "generated_at": GENERATED if hardware else None,
        "source_run_sha256": SHA_A if hardware else None,
        "asset_manifest_sha256": SHA_B if hardware else None,
        "authorization_id": "AUTH-OPT-001" if hardware else None,
        "timepoint": "t0",
        "timepoint_basis": "POF BUSY_N low-to-high + 60 s for t0",
        "geometry": "45/0",
        "illuminant": "D65",
        "observer": "2deg",
        "aperture_mm": 5.0 if hardware else None,
        "instrument_id": "COLOR-001" if hardware else None,
        "raw_capture_ref": "optical/raw-001.bin" if hardware else None,
        "raw_capture_sha256": SHA_C if hardware else None,
        "measurements": [
            {
                "roi_id": "ROI-CS1-001",
                "controller": "CS1",
                "x0": 0,
                "y0": 0,
                "x1": 64,
                "y1": 64,
                "intended_initial_code": 1,
                "measured_initial_lab": {"l": 95.0, "a": 0.0, "b": 0.0},
                "target_code": 3,
                "measured_final_lab": {"l": 50.0, "a": 60.0, "b": 40.0},
                "delta_e00": 1.0,
                "uniformity_delta_e00": 0.5,
                "ghosting_metric": 0.1,
            }
        ]
        if hardware
        else [],
    }


def rail(measured: bool, *, negative: bool = False) -> dict[str, object]:
    return {
        "minimum_v": (-22.0 if negative else 20.0) if measured else None,
        "maximum_v": (-20.0 if negative else 22.0) if measured else None,
        "plateau_v": (-21.0 if negative else 21.0) if measured else None,
        "rise_ms": 10.0 if measured else None,
        "release_ms": 12.0 if measured else None,
        "absolute_limit_known": False,
        "absolute_limit_reason": "no reviewed schema-v2 limit profile is allowlisted",
    }


def electrical_record(hardware: bool) -> dict[str, object]:
    maybe = (lambda value: value if hardware else None)
    return {
        "schema_version": 2,
        "kind": "mf1750-extended-color-electrical",
        "run_id": "RUN-001",
        "hardware_tested": hardware,
        "evidence_status": "partial" if hardware else "not_run",
        "null_reason": "absolute rail limits remain unqualified" if hardware else "electrical acquisition not run",
        "generated_at": GENERATED if hardware else None,
        "source_run_sha256": SHA_A if hardware else None,
        "asset_manifest_sha256": SHA_B if hardware else None,
        "authorization_id": "AUTH-ELEC-001" if hardware else None,
        "limit_profile": {
            "profile_id": None,
            "profile_version": None,
            "profile_sha256": None,
            "source_ref": None,
            "qualified": False,
        },
        "acquisition": {
            "instrument_ids": ["SCOPE-001"] if hardware else [],
            "sample_rate_sps": maybe(1_000_000.0),
            "bandwidth_hz": maybe(100_000.0),
            "clock_alignment_ms": maybe(0.5),
            "raw_trace_refs": ["scope/run-001.bin"] if hardware else [],
            "raw_trace_sha256": [SHA_C] if hardware else [],
        },
        "busy": {
            "pon_ms": maybe(10.0),
            "pon_asserted": maybe(True),
            "drf_ms": maybe(34187.0),
            "drf_asserted": maybe(True),
            "pof_ms": maybe(8.0),
            "pof_asserted": maybe(True),
            "timeout": maybe(False),
        },
        "input_power": {
            "peak_current_a": maybe(0.8),
            "mean_current_a": maybe(0.3),
            "rms_current_a": maybe(0.5),
            "energy_j": maybe(5.0),
            "tp1_min_v": maybe(3.1),
            "droop_v": maybe(0.2),
            "supply_cc_or_trip": maybe(False),
        },
        "rails": {
            "tp3_vph": rail(hardware),
            "tp5_prevgl": rail(hardware, negative=True),
            "tp6_vpc": rail(hardware, negative=True),
        },
        "temperatures": {
            key: maybe(value)
            for key, value in {
                "panel_c": 27.0,
                "controller_1_c": 30.0,
                "controller_2_c": 31.0,
                "q1_c": 32.0,
                "q2_c": 33.0,
                "l1_c": 34.0,
                "l2_c": 35.0,
            }.items()
        },
        "interlocks": {
            "estop_armed": maybe(True),
            "hardware_current_limit_armed": maybe(True),
            "j2_1_latched_switch_armed": maybe(True),
            "triggered": maybe(False),
        },
    }


def event_record(hardware: bool) -> dict[str, object]:
    event_names = (
        "power_off_confirmed",
        "power_on_authorized",
        "power_normal_confirmed",
        "frame_authorized",
        "pon",
        "drf",
        "pof",
        "operator_observation",
        "power_off_authorized",
        "tp1_zero_confirmed",
    )
    authorization_by_event = {
        "power_on_authorized": "AUTH-POWER-001",
        "frame_authorized": "AUTH-FRAME-001",
        "power_off_authorized": "AUTH-OFF-001",
    }
    return {
        "schema_version": 2,
        "kind": "mf1750-extended-color-event-recovery",
        "run_id": "RUN-001",
        "hardware_tested": hardware,
        "evidence_status": "complete" if hardware else "not_run",
        "null_reason": None if hardware else "event sequence not run",
        "generated_at": GENERATED if hardware else None,
        "source_run_sha256": SHA_A if hardware else None,
        "asset_manifest_sha256": SHA_B if hardware else None,
        "authorization_id": "AUTH-EVENT-001" if hardware else None,
        "events": [
            {
                "sequence": index,
                "timestamp": WHEN,
                "event": event_name,
                "authorization_id": authorization_by_event.get(event_name),
                "result": "pass",
                "details": None,
            }
            for index, event_name in enumerate(event_names)
        ] if hardware else [],
        "abnormality": {
            "observed": False,
            "category": None,
            "description": None,
            "fault_locked": False,
        },
        "automatic_retry_count": 0,
        "recovery": {
            "authorized": False,
            "authorization_id": None,
            "attempted": False,
            "sequence": [0, 1, 0, 1],
            "passed": None,
            "final_white_delta_e00": None,
            "raw_ghosting_metric": None,
        },
        "final_power_state": {
            "j2_1_off_confirmed": True if hardware else None,
            "tp1_v": 0.05 if hardware else None,
            "tp1_at_or_below_0_10_v_for_5s": True if hardware else None,
        },
    }


class RecordPositiveAndVersionTests(unittest.TestCase):
    def test_not_run_and_current_hardware_records_validate(self) -> None:
        for factory, validator in (
            (run_record, validate_run_record),
            (optical_record, validate_optical_record),
            (electrical_record, validate_electrical_record),
            (event_record, validate_event_recovery_record),
        ):
            for hardware in (False, True):
                with self.subTest(factory=factory.__name__, hardware=hardware):
                    validator(factory(hardware))

    def test_v1_is_explicitly_rejected(self) -> None:
        for factory, validator in (
            (run_record, validate_run_record),
            (optical_record, validate_optical_record),
            (electrical_record, validate_electrical_record),
            (event_record, validate_event_recovery_record),
        ):
            candidate = factory(False)
            candidate["schema_version"] = 1
            with self.subTest(factory=factory.__name__):
                with self.assertRaisesRegex(ExtendedColorRecordError, "identity"):
                    validator(candidate)


class RecordAttackTests(unittest.TestCase):
    def test_hardware_true_cannot_be_asserted_without_provenance(self) -> None:
        for factory, validator in (
            (run_record, validate_run_record),
            (optical_record, validate_optical_record),
            (electrical_record, validate_electrical_record),
            (event_record, validate_event_recovery_record),
        ):
            candidate = factory(False)
            candidate["hardware_tested"] = True
            with self.subTest(factory=factory.__name__):
                with self.assertRaises(ExtendedColorRecordError):
                    validator(candidate)

    def test_run_rejects_hash_authorization_time_and_identity_attacks(self) -> None:
        attacks = []
        missing_hash = run_record(True)
        missing_hash["frame_identity"]["controllers"][0]["dtm_sha256"] = None
        attacks.append(missing_hash)
        missing_auth = run_record(True)
        missing_auth["authorization"]["send_frame"] = authorization(False)
        attacks.append(missing_auth)
        reversed_time = run_record(True)
        reversed_time["started_at"], reversed_time["finished_at"] = LATER, WHEN
        attacks.append(reversed_time)
        wrong_fnv = run_record(True)
        wrong_fnv["frame_identity"]["frame_fnv1a"] = 0
        wrong_fnv["frame_identity"]["frame_fnv1a_hex"] = "0x00000000"
        attacks.append(wrong_fnv)
        late_authorization = run_record(True)
        late_authorization["authorization"]["send_frame"]["recorded_at"] = (
            "2026-08-05T21:03:00+08:00"
        )
        attacks.append(late_authorization)
        wrong_scope = run_record(True)
        wrong_scope["authorization_scope"]["test_id"] = "OTHER-TEST"
        attacks.append(wrong_scope)
        bool_r16 = run_record(True)
        bool_r16["panel"]["r16_ohm"] = False
        attacks.append(bool_r16)
        bool_mapping = run_record(True)
        bool_mapping["frame_identity"]["controllers"][0]["mapping"]["source_half"] = False
        attacks.append(bool_mapping)
        space_timestamp = run_record(True)
        space_timestamp["generated_at"] = "2026-08-05 21:02:00+08:00"
        attacks.append(space_timestamp)
        nonfinite = run_record(True)
        nonfinite["environment"]["temperature_c"] = math.nan
        attacks.append(nonfinite)
        for index, candidate in enumerate(attacks):
            with self.subTest(index=index):
                with self.assertRaises(ExtendedColorRecordError):
                    validate_run_record(candidate)

    def test_fault_locked_run_can_record_failure_before_frame_send(self) -> None:
        candidate = run_record(True)
        candidate["status"] = "fault_locked"
        candidate["evidence_status"] = "invalid"
        candidate["null_reason"] = "power-normal confirmation failed"
        candidate["abort_reason"] = "power rail outside expected polarity"
        for key in (
            "power_normal_confirmed",
            "send_frame",
            "post_refresh_confirmed",
            "final_power_off_tp1_confirmed",
        ):
            candidate["authorization"][key] = authorization(False)
        validate_run_record(candidate)

    def test_optical_rejects_wrong_science_roi_and_measurement_values(self) -> None:
        attacks = []
        wrong_illuminant = optical_record(True)
        wrong_illuminant["illuminant"] = "D50"
        attacks.append(wrong_illuminant)
        wrong_observer = optical_record(True)
        wrong_observer["observer"] = "10deg"
        attacks.append(wrong_observer)
        crossing_roi = optical_record(True)
        crossing_roi["measurements"][0]["x1"] = 600
        attacks.append(crossing_roi)
        missing_measurement = optical_record(True)
        missing_measurement["measurements"][0]["measured_final_lab"] = None
        attacks.append(missing_measurement)
        nonfinite = optical_record(True)
        nonfinite["measurements"][0]["measured_final_lab"]["l"] = math.inf
        attacks.append(nonfinite)
        for index, candidate in enumerate(attacks):
            with self.subTest(index=index):
                with self.assertRaises(ExtendedColorRecordError):
                    validate_optical_record(candidate)

    def test_electrical_rejects_trace_numeric_limit_and_interlock_attacks(self) -> None:
        attacks = []
        trace_mismatch = electrical_record(True)
        trace_mismatch["acquisition"]["raw_trace_sha256"] = []
        attacks.append(trace_mismatch)
        bool_number = electrical_record(True)
        bool_number["input_power"]["peak_current_a"] = True
        attacks.append(bool_number)
        impossible_current = electrical_record(True)
        impossible_current["input_power"]["mean_current_a"] = 0.9
        attacks.append(impossible_current)
        self_asserted_limit = electrical_record(True)
        self_asserted_limit["rails"]["tp3_vph"]["absolute_limit_known"] = True
        self_asserted_limit["rails"]["tp3_vph"]["absolute_limit_reason"] = None
        attacks.append(self_asserted_limit)
        qualified_profile = electrical_record(True)
        qualified_profile["limit_profile"] = {
            "profile_id": "UNREVIEWED",
            "profile_version": 1,
            "profile_sha256": "a" * 64,
            "source_ref": "limits/unreviewed.json",
            "qualified": True,
        }
        attacks.append(qualified_profile)
        wrong_polarity = electrical_record(True)
        wrong_polarity["rails"]["tp3_vph"].update(
            {"minimum_v": -22.0, "maximum_v": -20.0, "plateau_v": -21.0}
        )
        attacks.append(wrong_polarity)
        false_claim = electrical_record(False)
        false_claim["input_power"]["peak_current_a"] = 0.1
        attacks.append(false_claim)
        for index, candidate in enumerate(attacks):
            with self.subTest(index=index):
                with self.assertRaises(ExtendedColorRecordError):
                    validate_electrical_record(candidate)

    def test_electrical_complete_is_blocked_until_reviewed_limits_exist(self) -> None:
        candidate = electrical_record(True)
        candidate["evidence_status"] = "complete"
        candidate["null_reason"] = None
        with self.assertRaisesRegex(ExtendedColorRecordError, "unavailable"):
            validate_electrical_record(candidate)

    def test_invalid_electrical_record_preserves_reversed_polarity_evidence(self) -> None:
        candidate = electrical_record(True)
        candidate["evidence_status"] = "invalid"
        candidate["null_reason"] = "TP3 polarity reversed during acquisition"
        candidate["rails"]["tp3_vph"].update(
            {"minimum_v": -22.0, "maximum_v": -20.0, "plateau_v": -21.0}
        )
        validate_electrical_record(candidate)

    def test_event_record_rejects_order_auth_retry_recovery_and_power_attacks(self) -> None:
        attacks = []
        wrong_sequence = event_record(True)
        wrong_sequence["events"][0]["sequence"] = 1
        attacks.append(wrong_sequence)
        missing_auth = event_record(True)
        missing_auth["events"][1]["authorization_id"] = None
        attacks.append(missing_auth)
        retry = event_record(True)
        retry["automatic_retry_count"] = True
        attacks.append(retry)
        unauthorized_recovery = event_record(True)
        unauthorized_recovery["evidence_status"] = "partial"
        unauthorized_recovery["null_reason"] = "recovery evidence incomplete"
        unauthorized_recovery["recovery"]["attempted"] = True
        unauthorized_recovery["recovery"]["passed"] = False
        attacks.append(unauthorized_recovery)
        unsafe_power = event_record(True)
        unsafe_power["final_power_state"]["tp1_v"] = 0.2
        attacks.append(unsafe_power)
        for index, candidate in enumerate(attacks):
            with self.subTest(index=index):
                with self.assertRaises(ExtendedColorRecordError):
                    validate_event_recovery_record(candidate)

    def test_complete_event_requires_full_passed_ordered_chain(self) -> None:
        failed = event_record(True)
        failed["events"][7]["result"] = "fail"
        with self.assertRaisesRegex(ExtendedColorRecordError, "every event to pass"):
            validate_event_recovery_record(failed)

        missing = event_record(True)
        del missing["events"][5]
        for index, event in enumerate(missing["events"]):
            event["sequence"] = index
        with self.assertRaisesRegex(ExtendedColorRecordError, "exactly one drf"):
            validate_event_recovery_record(missing)

        reordered = event_record(True)
        reordered["events"][4]["event"], reordered["events"][5]["event"] = (
            reordered["events"][5]["event"],
            reordered["events"][4]["event"],
        )
        with self.assertRaisesRegex(ExtendedColorRecordError, "frozen refresh"):
            validate_event_recovery_record(reordered)

        fault = event_record(True)
        fault["events"].insert(
            8,
            {
                "sequence": 8,
                "timestamp": WHEN,
                "event": "fault",
                "authorization_id": None,
                "result": "pass",
                "details": "synthetic attack",
            },
        )
        for index, event in enumerate(fault["events"]):
            event["sequence"] = index
        with self.assertRaisesRegex(ExtendedColorRecordError, "fault event"):
            validate_event_recovery_record(fault)

        misplaced_flash = event_record(True)
        misplaced_flash["events"][5:5] = [
            {
                "sequence": 5,
                "timestamp": WHEN,
                "event": "flash_authorized",
                "authorization_id": "AUTH-FLASH-001",
                "result": "pass",
                "details": None,
            },
            {
                "sequence": 6,
                "timestamp": WHEN,
                "event": "flashed",
                "authorization_id": "AUTH-FLASH-001",
                "result": "pass",
                "details": None,
            },
        ]
        for index, event in enumerate(misplaced_flash["events"]):
            event["sequence"] = index
        with self.assertRaisesRegex(ExtendedColorRecordError, "complete flash events"):
            validate_event_recovery_record(misplaced_flash)


class RecordSchemaSecurityTests(unittest.TestCase):
    def schema_errors(self, name: str, record: dict[str, object]) -> list[object]:
        if Draft202012Validator is None or FormatChecker is None:
            self.skipTest("jsonschema is not installed")
        schema = json.loads(
            (REPO_ROOT / f"schemas/extended_color/{name}.schema.json").read_text(
                encoding="utf-8"
            )
        )
        return list(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(record)
        )

    def test_schema_and_semantic_validators_agree_on_current_positive_records(self) -> None:
        for name, factory, validator in (
            ("run", run_record, validate_run_record),
            ("optical", optical_record, validate_optical_record),
            ("electrical", electrical_record, validate_electrical_record),
            ("event_recovery", event_record, validate_event_recovery_record),
        ):
            for hardware in (False, True):
                with self.subTest(name=name, hardware=hardware):
                    candidate = factory(hardware)
                    self.assertEqual(self.schema_errors(name, candidate), [])
                    validator(candidate)

    def test_schema_and_semantic_validators_agree_on_critical_attacks(self) -> None:
        electrical_complete = electrical_record(True)
        electrical_complete["evidence_status"] = "complete"
        electrical_complete["null_reason"] = None

        not_run_with_power = electrical_record(False)
        not_run_with_power["input_power"]["peak_current_a"] = 0.1

        failed_complete_event = event_record(True)
        failed_complete_event["events"][7]["result"] = "fail"

        fault_complete_event = event_record(True)
        fault_complete_event["events"].insert(
            8,
            {
                "sequence": 8,
                "timestamp": WHEN,
                "event": "fault",
                "authorization_id": None,
                "result": "pass",
                "details": "synthetic attack",
            },
        )
        for index, event in enumerate(fault_complete_event["events"]):
            event["sequence"] = index

        partial_bad_lab = optical_record(True)
        partial_bad_lab["evidence_status"] = "partial"
        partial_bad_lab["null_reason"] = "bad Lab"
        partial_bad_lab["measurements"][0]["measured_final_lab"]["l"] = 1000.0

        for name, candidate, validator in (
            ("electrical", electrical_complete, validate_electrical_record),
            ("electrical", not_run_with_power, validate_electrical_record),
            ("event_recovery", failed_complete_event, validate_event_recovery_record),
            ("event_recovery", fault_complete_event, validate_event_recovery_record),
            ("optical", partial_bad_lab, validate_optical_record),
        ):
            with self.subTest(name=name):
                self.assertTrue(self.schema_errors(name, candidate))
                with self.assertRaises(ExtendedColorRecordError):
                    validator(candidate)

        fault = run_record(True)
        fault["status"] = "fault_locked"
        fault["evidence_status"] = "invalid"
        fault["null_reason"] = "power-normal confirmation failed"
        fault["abort_reason"] = "power rail outside expected polarity"
        for key in (
            "power_normal_confirmed",
            "send_frame",
            "post_refresh_confirmed",
            "final_power_off_tp1_confirmed",
        ):
            fault["authorization"][key] = authorization(False)
        self.assertEqual(self.schema_errors("run", fault), [])
        validate_run_record(fault)

    def test_v2_schemas_have_hardware_conditionals_and_missing_reason_contract(self) -> None:
        for name in ("run", "optical", "electrical", "event_recovery"):
            schema = json.loads(
                (REPO_ROOT / f"schemas/extended_color/{name}.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            with self.subTest(name=name):
                self.assertEqual(schema["properties"]["schema_version"]["const"], 2)
                self.assertIn("evidence_status", schema["required"])
                self.assertIn("null_reason", schema["required"])
                self.assertIn("allOf", schema)

    def test_electrical_limit_and_optical_science_contracts_are_explicit(self) -> None:
        electrical = json.loads(
            (REPO_ROOT / "schemas/extended_color/electrical.schema.json").read_text(
                encoding="utf-8"
            )
        )
        rail = electrical["$defs"]["rail"]
        self.assertFalse(rail["properties"]["absolute_limit_known"]["const"])
        self.assertIn("absolute_limit_reason", rail["required"])
        self.assertIn("limit_profile", electrical["required"])
        complete_conditions = [
            item
            for item in electrical["allOf"]
            if item.get("if", {}).get("properties", {}).get("evidence_status", {}).get("const")
            == "complete"
        ]
        self.assertEqual(len(complete_conditions), 1)
        self.assertIs(complete_conditions[0]["then"], False)

        optical = json.loads(
            (REPO_ROOT / "schemas/extended_color/optical.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(optical["properties"]["illuminant"]["const"], "D65")
        self.assertEqual(optical["properties"]["observer"]["const"], "2deg")
        self.assertEqual(optical["$defs"]["lab"]["properties"]["l"]["maximum"], 100)

        event = json.loads(
            (REPO_ROOT / "schemas/extended_color/event_recovery.schema.json").read_text(
                encoding="utf-8"
            )
        )
        complete_event = next(
            item
            for item in event["allOf"]
            if item.get("if", {}).get("properties", {}).get("evidence_status", {}).get("const")
            == "complete"
        )
        self.assertEqual(
            complete_event["then"]["properties"]["events"]["items"]["properties"]["result"]["const"],
            "pass",
        )


if __name__ == "__main__":
    unittest.main()
