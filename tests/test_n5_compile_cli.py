from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest

from host.extended_color.execution import compile_execution_contract
from tools import mf1750_n5_measurement_campaign as campaign


def _production_profile() -> dict[str, object]:
    panel = {**campaign.DEFAULT_PANEL, "serial": "PANEL-N5-PRODUCTION-TEST-001"}
    cold = campaign.reviewed_panel_cold_profile(
        minimum_panel_power_off_seconds=60,
        review_artifact_sha256="1" * 64,
    )
    recovery = campaign.build_reviewed_transition_recovery_profile(
        panel=panel,
        firmware=campaign.DEFAULT_FIRMWARE,
        waveform_id="wf-n5-production-test-v1",
        waveform_sha256="2" * 64,
        qualification_artifact_sha256="3" * 64,
        reviewer_id="n5-production-test-reviewer",
        reviewed_at="2026-08-08T12:00:00+08:00",
        review_artifact_sha256="4" * 64,
        supplier_limit_profile_sha256="5" * 64,
        usage_limit_contract_sha256="6" * 64,
        temperature_chain_sha256="7" * 64,
    )
    return campaign.seal_compile_profile(
        {
            "schema_version": 1,
            "kind": campaign.COMPILE_PROFILE_KIND,
            "panel": panel,
            "firmware": campaign.DEFAULT_FIRMWARE,
            "formal_palette_cold_profile": cold,
            "formal_transition_recovery_profile": recovery,
            "formal_transition_power_profile": cold,
            "waveform_id": "wf-n5-production-test-v1",
            "waveform_sha256": "2" * 64,
            "temperature_c": 23.0,
            "relative_humidity_percent": 45.0,
            "environment_record_sha256": "8" * 64,
            "standard_table_canonical_sha256": "9" * 64,
            "instrument_qualification_canonical_sha256": "a" * 64,
            "pixel_pitch_review_artifact_sha256": "b" * 64,
            "roi_aperture_fit_review_artifact_sha256": "c" * 64,
            "orientation_bias_max_delta_e00": 1.0,
            "u95_max_delta_e00": 1.0,
            "acceptance_span_delta_e00": 5.0,
            "acceptance_review_artifact_sha256": "d" * 64,
            "acquisition_feasibility_review_artifact_sha256": "e" * 64,
        }
    )


class N5CompileCliTests(unittest.TestCase):
    def test_compile_publishes_one_deeply_valid_full_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile_file = root / "profile.json"
            output_file = root / "manifest.json"
            profile_file.write_bytes(campaign.canonical_json_bytes(_production_profile()))

            result = campaign.compile_manifest_file(profile_file, output_file)
            stored = json.loads(output_file.read_text(encoding="utf-8"))
            contract = compile_execution_contract(stored)

            self.assertEqual(result["declared_actions"], 73)
            self.assertEqual(result["declared_sessions"], 26)
            self.assertTrue(result["atomic_exclusive_create"])
            self.assertTrue(result["deep_validation_passed"])
            self.assertEqual(len(contract["actions"]), 73)
            self.assertEqual(len(contract["sessions"]), 26)
            self.assertEqual(
                output_file.read_bytes(), campaign.canonical_json_bytes(stored)
            )

    def test_compile_refuses_an_existing_destination_without_changing_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile_file = root / "profile.json"
            output_file = root / "manifest.json"
            profile_file.write_bytes(campaign.canonical_json_bytes(_production_profile()))
            sentinel = b"pre-existing-owner-bytes"
            output_file.write_bytes(sentinel)

            with self.assertRaisesRegex(campaign.N5CampaignError, "already exists"):
                campaign.compile_manifest_file(profile_file, output_file)

            self.assertEqual(output_file.read_bytes(), sentinel)

    def test_atomic_publisher_has_exactly_one_concurrent_winner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "exclusive.json"
            payloads = (b'{"winner":1}', b'{"winner":2}')

            def publish(payload: bytes) -> tuple[str, bytes]:
                try:
                    campaign._publish_new_bytes(destination, payload)
                except campaign.N5CampaignError:
                    return "rejected", payload
                return "published", payload

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(publish, payloads))

            winners = [payload for status, payload in results if status == "published"]
            self.assertEqual(len(winners), 1)
            self.assertEqual(destination.read_bytes(), winners[0])
            self.assertEqual(
                sorted(status for status, _payload in results),
                ["published", "rejected"],
            )

    def test_compile_profile_duplicate_key_is_rejected_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile_file = root / "profile.json"
            output_file = root / "manifest.json"
            profile_file.write_text(
                '{"schema_version":1,"schema_version":1}', encoding="utf-8"
            )

            with self.assertRaisesRegex(campaign.N5CampaignError, "duplicate key"):
                campaign.compile_manifest_file(profile_file, output_file)

            self.assertFalse(output_file.exists())


if __name__ == "__main__":
    unittest.main()
