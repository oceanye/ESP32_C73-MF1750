from __future__ import annotations

from copy import deepcopy
import hashlib
import hmac
from pathlib import Path
import tempfile
import unittest

from host.visible_refresh_campaign import canonical_json_bytes
from tools import mf1750_n5_measurement_campaign as source
from tools import mf1750_n5_physical_campaign as physical


FIRMWARE_BYTES = b"n5-physical-campaign-test-rc2g-firmware-v1\x00\x01"
FIRMWARE = {
    **source.DEFAULT_FIRMWARE,
    "binary_sha256": hashlib.sha256(FIRMWARE_BYTES).hexdigest(),
}
PANEL = {
    **source.DEFAULT_PANEL,
    "serial": "MF1750-N5-LAB-0001",
}
REVIEW_EVIDENCE = b"reviewed N5 static science and physical binding\n"
TRUSTED_KEY = b"n5-static-science-review-test-key-v1"
ATTACKER_KEY = b"attacker-self-approval-key"
INTERVAL_SECONDS = 180.0
COOLDOWN_SECONDS = 240.0


def _compile_profile() -> dict[str, object]:
    cold = source.reviewed_panel_cold_profile(
        minimum_panel_power_off_seconds=60,
        review_artifact_sha256="1" * 64,
    )
    recovery = source.build_reviewed_transition_recovery_profile(
        panel=PANEL,
        firmware=FIRMWARE,
        waveform_id="wf-n5-physical-test-v1",
        waveform_sha256="2" * 64,
        qualification_artifact_sha256="3" * 64,
        reviewer_id="n5-static-science-reviewer",
        reviewed_at="2026-08-08T12:00:00+08:00",
        review_artifact_sha256="4" * 64,
        supplier_limit_profile_sha256="5" * 64,
        usage_limit_contract_sha256="6" * 64,
        temperature_chain_sha256="7" * 64,
    )
    return source.seal_compile_profile(
        {
            "schema_version": 1,
            "kind": source.COMPILE_PROFILE_KIND,
            "panel": PANEL,
            "firmware": FIRMWARE,
            "formal_palette_cold_profile": cold,
            "formal_transition_recovery_profile": recovery,
            "formal_transition_power_profile": cold,
            "waveform_id": "wf-n5-physical-test-v1",
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


def _inputs(*, key: bytes = TRUSTED_KEY) -> physical.N5PhysicalCampaignInputs:
    profile = _compile_profile()
    profile_bytes = canonical_json_bytes(profile)
    manifest = source.compile_manifest_from_profile(profile)
    manifest_bytes = canonical_json_bytes(manifest)
    # A production invocation normally points at the N2 physical campaign.
    # The already physical-serial-bound P0 is an exact compatible anchor for
    # this isolated materializer test.
    anchor = manifest["shared_p0"]
    anchor_bytes = canonical_json_bytes(anchor)
    approval = physical.create_static_science_review_approval(
        reviewer_id="trusted-static-science-reviewer",
        reviewed_at="2026-08-08T12:30:00+08:00",
        science_review_evidence=REVIEW_EVIDENCE,
        compile_profile=profile,
        compile_profile_bytes=profile_bytes,
        source_manifest=manifest,
        source_manifest_bytes=manifest_bytes,
        physical_anchor=anchor,
        physical_anchor_bytes=anchor_bytes,
        firmware_binary=FIRMWARE_BYTES,
        minimum_interval_seconds=INTERVAL_SECONDS,
        planned_cooldown_seconds=COOLDOWN_SECONDS,
        reviewer_key=key,
    )
    return physical.N5PhysicalCampaignInputs(
        compile_profile=profile,
        compile_profile_bytes=profile_bytes,
        source_manifest=manifest,
        source_manifest_bytes=manifest_bytes,
        physical_anchor=anchor,
        physical_anchor_bytes=anchor_bytes,
        firmware_binary=FIRMWARE_BYTES,
        science_review_evidence=REVIEW_EVIDENCE,
        science_review_approval=approval,
        science_review_approval_bytes=canonical_json_bytes(approval),
        reviewer_key=key,
    )


class N5PhysicalCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = _inputs()
        cls.plan = physical.compile_n5_physical_plan(
            cls.inputs,
            namespace="physical-test-v1",
            minimum_interval_seconds=INTERVAL_SECONDS,
            planned_cooldown_seconds=COOLDOWN_SECONDS,
        )

    def test_rebuilds_full_73_action_26_session_identity_closure(self) -> None:
        plan = self.plan
        rebound = plan["physical_rebind"]
        campaign = rebound["physical_campaign"]
        contract = plan["execution_contract"]

        self.assertEqual(len(campaign["actions"]), 73)
        self.assertEqual(len(campaign["sessions"]), 26)
        self.assertEqual(len(rebound["action_identity_map"]), 73)
        self.assertEqual(len(contract["actions"]), 73)
        self.assertEqual(len(contract["sessions"]), 26)
        self.assertEqual(contract["p0_campaign"], campaign)
        self.assertEqual(plan["runtime_manifest"]["campaign_id"], campaign["campaign_id"])
        self.assertEqual(
            plan["operator_process_schedule"]["classification"],
            physical.PROCESS_SCHEDULE_CLASSIFICATION,
        )
        self.assertTrue(plan["operator_process_schedule"]["not_a_supplier_rating"])

        old_actions = {
            action["action_identity_sha256"]
            for action in self.inputs.source_manifest["shared_p0"]["actions"]
        }
        new_actions = {
            action["action_identity_sha256"] for action in campaign["actions"]
        }
        old_claims = {
            action["claim"]["filename"]
            for action in self.inputs.source_manifest["shared_p0"]["actions"]
        }
        new_claims = {
            action["claim"]["filename"] for action in campaign["actions"]
        }
        self.assertTrue(old_actions.isdisjoint(new_actions))
        self.assertTrue(old_claims.isdisjoint(new_claims))
        self.assertTrue(
            all(
                action["identity"]["schedule"][
                    "minimum_interval_since_prior_seconds"
                ]
                == INTERVAL_SECONDS
                for action in campaign["actions"]
                if action["identity"]["prior"] is not None
            )
        )
        self.assertTrue(
            all(
                session["planned_cooldown_seconds"] == COOLDOWN_SECONDS
                for session in campaign["sessions"]
            )
        )

    def test_full_replay_is_canonical_exact(self) -> None:
        replay = physical.validate_n5_physical_plan(
            self.plan,
            self.inputs,
            namespace="physical-test-v1",
            minimum_interval_seconds=INTERVAL_SECONDS,
            planned_cooldown_seconds=COOLDOWN_SECONDS,
        )
        self.assertEqual(replay, self.plan)
        self.assertEqual(canonical_json_bytes(replay), canonical_json_bytes(self.plan))

    def test_file_materializer_reads_actual_canonical_artifact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def publish(name: str, payload: bytes) -> Path:
                path = root / name
                path.write_bytes(payload)
                return path

            profile_file = publish(
                "compile-profile.json", self.inputs.compile_profile_bytes
            )
            source_file = publish(
                "source-manifest.json", self.inputs.source_manifest_bytes
            )
            anchor_file = publish(
                "physical-anchor.json", self.inputs.physical_anchor_bytes
            )
            firmware_file = publish("firmware.bin", self.inputs.firmware_binary)
            evidence_file = publish(
                "science-review.bin", self.inputs.science_review_evidence
            )
            approval_file = publish(
                "science-approval.json",
                self.inputs.science_review_approval_bytes,
            )
            key_file = publish("science-reviewer.key", self.inputs.reviewer_key)
            replay = physical.compile_n5_physical_plan_from_files(
                compile_profile_file=profile_file,
                source_manifest_file=source_file,
                physical_anchor_campaign_file=anchor_file,
                firmware_binary_file=firmware_file,
                science_review_evidence_file=evidence_file,
                science_review_approval_file=approval_file,
                reviewer_key_file=key_file,
                namespace="physical-test-v1",
                minimum_interval_seconds=INTERVAL_SECONDS,
                planned_cooldown_seconds=COOLDOWN_SECONDS,
            )
            self.assertEqual(replay, self.plan)

    def test_self_approved_or_forged_review_is_rejected(self) -> None:
        attacker_inputs = _inputs(key=ATTACKER_KEY)
        attacker_inputs = physical.N5PhysicalCampaignInputs(
            **{
                **attacker_inputs.__dict__,
                "reviewer_key": TRUSTED_KEY,
            }
        )
        with self.assertRaisesRegex(
            physical.N5PhysicalCampaignError,
            "trusted reviewer key|HMAC",
        ):
            physical.compile_n5_physical_plan(
                attacker_inputs,
                namespace="physical-test-v1",
                minimum_interval_seconds=INTERVAL_SECONDS,
                planned_cooldown_seconds=COOLDOWN_SECONDS,
            )

        forged = deepcopy(self.inputs.science_review_approval)
        forged["authentication"]["signature"] = "f" * 64
        forged_inputs = physical.N5PhysicalCampaignInputs(
            **{
                **self.inputs.__dict__,
                "science_review_approval": forged,
                "science_review_approval_bytes": canonical_json_bytes(forged),
            }
        )
        with self.assertRaisesRegex(physical.N5PhysicalCampaignError, "HMAC"):
            physical.compile_n5_physical_plan(
                forged_inputs,
                namespace="physical-test-v1",
                minimum_interval_seconds=INTERVAL_SECONDS,
                planned_cooldown_seconds=COOLDOWN_SECONDS,
            )

    def test_actual_review_firmware_and_schedule_drift_fail_closed(self) -> None:
        changed_review = physical.N5PhysicalCampaignInputs(
            **{
                **self.inputs.__dict__,
                "science_review_evidence": REVIEW_EVIDENCE + b"tamper",
            }
        )
        with self.assertRaisesRegex(
            physical.N5PhysicalCampaignError, "exact physical compiler inputs"
        ):
            physical.compile_n5_physical_plan(
                changed_review,
                namespace="physical-test-v1",
                minimum_interval_seconds=INTERVAL_SECONDS,
                planned_cooldown_seconds=COOLDOWN_SECONDS,
            )

        changed_firmware = physical.N5PhysicalCampaignInputs(
            **{**self.inputs.__dict__, "firmware_binary": FIRMWARE_BYTES + b"tamper"}
        )
        with self.assertRaisesRegex(
            physical.N5PhysicalCampaignError, "firmware bytes"
        ):
            physical.compile_n5_physical_plan(
                changed_firmware,
                namespace="physical-test-v1",
                minimum_interval_seconds=INTERVAL_SECONDS,
                planned_cooldown_seconds=COOLDOWN_SECONDS,
            )

        with self.assertRaisesRegex(
            physical.N5PhysicalCampaignError, "exact physical compiler inputs"
        ):
            physical.compile_n5_physical_plan(
                self.inputs,
                namespace="physical-test-v1",
                minimum_interval_seconds=INTERVAL_SECONDS + 1,
                planned_cooldown_seconds=COOLDOWN_SECONDS,
            )

    def test_hmac_uses_constant_time_comparison_contract(self) -> None:
        # White-box regression: the approval's expected signature really is a
        # canonical detached HMAC, while validation uses compare_digest.
        approval = self.inputs.science_review_approval
        expected = hmac.new(
            TRUSTED_KEY,
            physical._approval_unsigned_bytes(approval),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(approval["authentication"]["signature"], expected)


if __name__ == "__main__":
    unittest.main()
