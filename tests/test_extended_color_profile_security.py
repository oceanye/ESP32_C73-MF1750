from __future__ import annotations

import json
import math
from pathlib import Path
import unittest

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # pragma: no cover - optional local contract audit dependency
    Draft202012Validator = None
    FormatChecker = None

from host.extended_color import (
    NULL_MEASUREMENT_FIELDS,
    build_empty_transition_profile,
    validate_transition_profile,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def measured_profile() -> dict[str, object]:
    profile = build_empty_transition_profile()
    profile["hardware_tested"] = True
    profile["generated_at"] = "2026-08-05T21:00:00+08:00"
    profile["panel_serial"] = "PANEL-001"
    profile["firmware_git_commit"] = "d" * 40
    profile["firmware_binary_sha256"] = "e" * 64
    profile["waveform_id"] = "factory-v1"
    profile["waveform_sha256"] = "f" * 64
    profile["environment"] = {
        "temperature_c": 25.0,
        "relative_humidity_percent": 50.0,
        "record_ref": "environment/profile-001.json",
    }
    profile["illuminant"] = "D65"
    profile["observer"] = "2deg"
    profile["geometry"] = "45/0"
    cell = profile["cells"][0]
    cell.update(
        {
            "sample_count": 5,
            "initial_lab_mean": {"l": 95.0, "a": 0.1, "b": -0.2},
            "final_lab_mean": {"l": 50.0, "a": 60.0, "b": 40.0},
            "delta_e00_mean": 1.5,
            "delta_e00_sd": 0.2,
            "cs1_minus_cs2_delta_e00": -0.1,
            "position_effect_delta_e00": 0.3,
            "ghosting_metric_mean": 0.4,
            "busy_ms_mean": 34187.0,
            "peak_current_a_mean": 0.8,
            "energy_j_mean": 5.2,
            "temperature_rise_c_mean": 2.0,
            "recovery_pass_rate": 1.0,
            "source_run_sha256s": [f"{index:064x}" for index in range(1, 6)],
            "asset_manifest_sha256s": [f"{index:064x}" for index in range(101, 106)],
            "authorization_ids": [f"AUTH-{index:03d}" for index in range(1, 6)],
        }
    )
    return profile


class TransitionProfileSecurityTests(unittest.TestCase):
    def schema_errors(self, profile: dict[str, object]) -> list[object]:
        if Draft202012Validator is None or FormatChecker is None:
            self.skipTest("jsonschema is not installed")
        schema = json.loads(
            (REPO_ROOT / "schemas/extended_color/transition_profile.schema.json").read_text(
                encoding="utf-8"
            )
        )
        return list(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(profile)
        )

    def test_empty_and_complete_measured_profiles_are_valid(self) -> None:
        validate_transition_profile(build_empty_transition_profile())
        validate_transition_profile(measured_profile())

    def test_positive_sample_requires_every_measurement(self) -> None:
        for field in NULL_MEASUREMENT_FIELDS:
            with self.subTest(field=field):
                candidate = measured_profile()
                candidate["cells"][0][field] = None
                with self.assertRaisesRegex(ValueError, "with samples must provide"):
                    validate_transition_profile(candidate)

    def test_nonfinite_bool_and_out_of_range_values_fail_closed(self) -> None:
        attacks = [
            ("delta_e00_mean", math.nan),
            ("energy_j_mean", math.inf),
            ("busy_ms_mean", True),
            ("peak_current_a_mean", -0.01),
            ("recovery_pass_rate", 1.01),
            ("position_effect_delta_e00", -1.0),
            ("temperature_rise_c_mean", -201.0),
        ]
        for field, value in attacks:
            with self.subTest(field=field, value=value):
                candidate = measured_profile()
                candidate["cells"][0][field] = value
                with self.assertRaises(ValueError):
                    validate_transition_profile(candidate)

        for component, value in (("l", 101.0), ("a", math.nan), ("b", False)):
            with self.subTest(component=component):
                candidate = measured_profile()
                candidate["cells"][0]["final_lab_mean"][component] = value
                with self.assertRaises(ValueError):
                    validate_transition_profile(candidate)

    def test_sample_count_and_hardware_timestamp_must_agree(self) -> None:
        attacks = []

        false_with_samples = measured_profile()
        false_with_samples["hardware_tested"] = False
        false_with_samples["generated_at"] = None
        attacks.append(false_with_samples)

        true_without_samples = build_empty_transition_profile()
        true_without_samples["hardware_tested"] = True
        true_without_samples["generated_at"] = "2026-08-05T21:00:00+08:00"
        attacks.append(true_without_samples)

        false_with_time = build_empty_transition_profile()
        false_with_time["generated_at"] = "2026-08-05T21:00:00+08:00"
        attacks.append(false_with_time)

        naive_time = measured_profile()
        naive_time["generated_at"] = "2026-08-05T21:00:00"
        attacks.append(naive_time)

        space_time = measured_profile()
        space_time["generated_at"] = "2026-08-05 21:00:00+08:00"
        attacks.append(space_time)

        second_offset = measured_profile()
        second_offset["generated_at"] = "2026-08-05T21:00:00+08:00:30"
        attacks.append(second_offset)

        bool_count = build_empty_transition_profile()
        bool_count["cells"][0]["sample_count"] = True
        attacks.append(bool_count)

        huge_count = measured_profile()
        huge_count["cells"][0]["sample_count"] = 1_000_001
        attacks.append(huge_count)

        for index, candidate in enumerate(attacks):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    validate_transition_profile(candidate)

    def test_measured_profile_requires_science_and_per_sample_provenance(self) -> None:
        attacks = []
        for field, value in (
            ("panel_serial", None),
            ("firmware_git_commit", None),
            ("firmware_binary_sha256", None),
            ("waveform_id", None),
            ("waveform_sha256", None),
            ("illuminant", "D50"),
            ("observer", "10deg"),
            ("geometry", "d/8"),
        ):
            candidate = measured_profile()
            candidate[field] = value
            attacks.append(candidate)
        missing_run = measured_profile()
        missing_run["cells"][0]["source_run_sha256s"] = None
        attacks.append(missing_run)
        short_auth = measured_profile()
        short_auth["cells"][0]["authorization_ids"] = ["AUTH-001"]
        attacks.append(short_auth)
        duplicate_manifest = measured_profile()
        duplicate_manifest["cells"][0]["asset_manifest_sha256s"] = ["a" * 64] * 5
        attacks.append(duplicate_manifest)
        for index, candidate in enumerate(attacks):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    validate_transition_profile(candidate)

    def test_boolean_color_codes_do_not_alias_integer_codes(self) -> None:
        candidate = measured_profile()
        candidate["color_codes"][0] = False
        for cell in candidate["cells"]:
            if cell["old_code"] == 0:
                cell["old_code"] = False
        with self.assertRaises(ValueError):
            validate_transition_profile(candidate)

    def test_schema_and_semantic_profile_contracts_agree(self) -> None:
        for candidate in (build_empty_transition_profile(), measured_profile()):
            with self.subTest(hardware=candidate["hardware_tested"]):
                self.assertEqual(self.schema_errors(candidate), [])
                validate_transition_profile(candidate)

        attacks = []
        d50 = measured_profile()
        d50["illuminant"] = "D50"
        attacks.append(d50)
        missing_provenance = measured_profile()
        missing_provenance["cells"][0]["source_run_sha256s"] = None
        attacks.append(missing_provenance)
        unsafe_time = measured_profile()
        unsafe_time["generated_at"] = "2026-08-05 21:00:00+08:00"
        attacks.append(unsafe_time)
        for index, candidate in enumerate(attacks):
            with self.subTest(index=index):
                self.assertTrue(self.schema_errors(candidate))
                with self.assertRaises(ValueError):
                    validate_transition_profile(candidate)

    def test_profile_schema_contains_cell_and_hardware_conditionals(self) -> None:
        schema = json.loads(
            (REPO_ROOT / "schemas/extended_color/transition_profile.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("allOf", schema)
        cell = schema["$defs"]["cell"]
        self.assertIn("allOf", cell)
        self.assertIn("nullable_lab", schema["$defs"])
        self.assertEqual(
            cell["properties"]["sample_count"]["maximum"],
            1_000_000,
        )


if __name__ == "__main__":
    unittest.main()
