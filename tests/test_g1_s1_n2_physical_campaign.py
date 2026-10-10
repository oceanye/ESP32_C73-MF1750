from __future__ import annotations

from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.visible_refresh_campaign import (
    canonical_json_bytes,
    evaluate_limit_profile,
    validate_campaign_contract,
    validate_limit_profile,
)
from host.visible_refresh_campaign import production_profile as production
from tools import g1_s1_n2_physical_campaign as physical
from tools import g1_s1_rc2g_n2_photo_campaign as frozen


PANEL = {
    "model": "MF1750-C73",
    "serial": "MF1750-LAB-PANEL-0001",
    "board_id": "ESP32-C73",
    "pcb_revision": "rev-a1",
}
REVIEW_BYTES = b"unit-test physical panel binding review artifact v1\n"
PROCESS_SCHEDULE = {
    "minimum_interval_seconds": 150,
    "planned_cooldown_seconds": 150,
}
EXPECTED_FIXTURE_BINDING_SHA256 = (
    "3d00da4e31b38355e80ea9a441326cf5009cc35f8bfd333969630dd86c3c7566"
)
EXPECTED_FIXTURE_CAMPAIGN_CANONICAL_SHA256 = (
    "3a29450496ec84f93a92961cd914e67f4cf9e743bd1bc9bb9de7351d3260d9e3"
)
EXPECTED_FIXTURE_CAMPAIGN_FILE_SHA256 = (
    "a164eb32fc6288a19e3d33a221f36168eccfa9acd90cdc37d2472e818bf5c1d9"
)
EXPECTED_FIXTURE_OPERATOR_CANONICAL_SHA256 = (
    "4e69d759e04074b51f34ac02048ecfe8b7a037219154086994b39de78c9e8eaa"
)
EXPECTED_FIXTURE_OPERATOR_FILE_SHA256 = (
    "c189210366384d827f1ce745dbad6c0895221c8ff385bbba9f7c88f0ecefb33e"
)


def _action_map(campaign):
    return {
        f"{action['identity']['cell_id'].lower()}-{action['identity']['phase']}": action
        for action in campaign["actions"]
    }


class N2PhysicalCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frozen_manifest = frozen.compile_campaign_manifest()

    def setUp(self) -> None:
        hardware = physical.REPO_ROOT / ".test-output" / "hardware"
        self.temporary = tempfile.TemporaryDirectory(dir=hardware)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source_file = self.root / "frozen-source.json"
        self.source_file.write_bytes(canonical_json_bytes(self.frozen_manifest))
        self.panel_file = self.root / "physical-panel.json"
        self.panel_file.write_bytes(canonical_json_bytes(PANEL))
        self.review_file = self.root / "binding-review.bin"
        self.review_file.write_bytes(REVIEW_BYTES)
        self.compile_patch = mock.patch.object(
            physical.frozen,
            "compile_campaign_manifest",
            side_effect=lambda: deepcopy(self.frozen_manifest),
        )
        self.compile_patch.start()
        self.addCleanup(self.compile_patch.stop)

    def _compile(self):
        return physical.compile_physical_manifest_from_files(
            self.source_file,
            self.panel_file,
            self.review_file,
            **PROCESS_SCHEDULE,
        )

    def _write_manifest(self, name: str, manifest) -> Path:
        path = self.root / name
        path.write_bytes(canonical_json_bytes(manifest))
        return path

    def test_materializes_exact_physical_campaign_with_all_new_identities(self) -> None:
        manifest = self._compile()
        campaign = manifest["physical_campaign_contract"]
        binding_sha = manifest["physical_binding"]["integrity"]["canonical_sha256"]
        validate_campaign_contract(campaign)
        self.assertEqual(campaign["panel"], PANEL)
        materialization_sha = physical._sha256(
            canonical_json_bytes(
                {
                    "physical_binding_canonical_sha256": binding_sha,
                    "operator_process_schedule": manifest[
                        "operator_process_schedule"
                    ],
                }
            )
        )
        self.assertEqual(
            campaign["campaign_id"],
            f"{physical.PHYSICAL_CAMPAIGN_ID_PREFIX}{materialization_sha}",
        )
        self.assertEqual(manifest["source"]["offline_panel"], frozen.PANEL_CONTRACT)
        self.assertEqual(tuple(manifest["fixed_actions"]), physical.FIXED_ACTION_KEYS)
        self.assertEqual(
            manifest["operator_process_schedule"],
            {
                "schema_version": 1,
                "kind": physical.PROCESS_SCHEDULE_KIND,
                "classification": physical.PROCESS_SCHEDULE_CLASSIFICATION,
                "not_a_supplier_rating": True,
                **PROCESS_SCHEDULE,
            },
        )
        self.assertEqual(binding_sha, EXPECTED_FIXTURE_BINDING_SHA256)
        self.assertEqual(
            campaign["integrity"]["canonical_sha256"],
            EXPECTED_FIXTURE_CAMPAIGN_CANONICAL_SHA256,
        )
        self.assertEqual(
            manifest["physical_campaign_file"]["file_sha256"],
            EXPECTED_FIXTURE_CAMPAIGN_FILE_SHA256,
        )
        self.assertEqual(
            manifest["integrity"]["canonical_sha256"],
            EXPECTED_FIXTURE_OPERATOR_CANONICAL_SHA256,
        )
        self.assertEqual(
            physical.manifest_file_sha256(manifest),
            EXPECTED_FIXTURE_OPERATOR_FILE_SHA256,
        )

        old_by_key = _action_map(self.frozen_manifest["p0_campaign_contract"])
        new_by_key = _action_map(campaign)
        old_hashes = {action["action_identity_sha256"] for action in old_by_key.values()}
        new_hashes = {action["action_identity_sha256"] for action in new_by_key.values()}
        old_claims = {action["claim"]["filename"] for action in old_by_key.values()}
        new_claims = {action["claim"]["filename"] for action in new_by_key.values()}
        self.assertEqual(len(new_hashes), 8)
        self.assertTrue(old_hashes.isdisjoint(new_hashes))
        self.assertTrue(old_claims.isdisjoint(new_claims))
        for key in physical.FIXED_ACTION_KEYS:
            with self.subTest(action=key):
                old = old_by_key[key]["identity"]
                new = new_by_key[key]["identity"]
                self.assertEqual(new["frame"], old["frame"])
                self.assertEqual(new["request"], old["request"])
                self.assertEqual(
                    new["schedule"]["minimum_interval_since_prior_seconds"],
                    0 if key.endswith("map-primer") else 150,
                )
                self.assertTrue(new["schedule"]["counts_as_visible_refresh"])
                self.assertNotEqual(
                    new_by_key[key]["action_identity_sha256"],
                    old_by_key[key]["action_identity_sha256"],
                )
        for cell in range(1, 5):
            primer = new_by_key[f"q{cell}-map-primer"]
            target = new_by_key[f"q{cell}-target"]
            self.assertEqual(
                target["identity"]["prior"]["action_identity_sha256"],
                primer["action_identity_sha256"],
            )
        self.assertTrue(
            all(
                session["planned_cooldown_seconds"] == 150
                for session in campaign["sessions"]
            )
        )

    def test_review_artifact_is_hashed_and_source_candidates_are_retained(self) -> None:
        manifest = self._compile()
        artifact = manifest["physical_binding"]["binding_review_artifact"]
        self.assertEqual(artifact["bytes"], len(REVIEW_BYTES))
        self.assertEqual(artifact["sha256"], physical._sha256(REVIEW_BYTES))
        expected = [
            (
                cell["cell_id"],
                cell["algorithm"],
                cell["candidate"]["frame"]["sha256"],
            )
            for cell in self.frozen_manifest["cells"]
        ]
        actual = [
            (record["cell_id"], record["algorithm"], record["frame_sha256"])
            for record in manifest["source"]["candidate_bindings"]
        ]
        self.assertEqual(actual, expected)
        self.assertEqual(
            manifest["source"]["outer_manifest_file_sha256"],
            physical.SOURCE_OUTER_FILE_SHA256,
        )

    def test_limit_profile_is_only_an_unapproved_all_null_draft(self) -> None:
        manifest = self._compile()
        campaign = manifest["physical_campaign_contract"]
        draft = manifest["limit_profile_draft"]
        validate_limit_profile(draft)
        decision = evaluate_limit_profile(draft, evaluated_at="2026-08-08T12:00:00Z")
        self.assertFalse(decision.hardware_ready)
        self.assertFalse(draft["review"]["approved"])
        self.assertTrue(all(value is None for value in draft["limits"].values()))
        self.assertTrue(all(value is None for value in draft["usage"].values()))
        self.assertTrue(all(value is None for value in draft["validity"].values()))
        self.assertEqual(draft["panel"], campaign["panel"])
        self.assertEqual(draft["firmware"], campaign["firmware"])
        self.assertEqual(len(draft["action_allowlist"]), 8)
        notice = manifest["limit_profile_draft_notice"]
        self.assertFalse(notice["approved"])
        self.assertFalse(notice["execution_eligible"])
        self.assertTrue(notice["must_be_completed_reviewed_and_resealed_separately"])

    def test_same_inputs_are_deterministic_and_binding_changes_rotate_every_action(self) -> None:
        first = self._compile()
        second = self._compile()
        self.assertEqual(first, second)
        self.assertEqual(
            physical.manifest_file_sha256(first),
            physical.manifest_file_sha256(second),
        )

        other_panel = {**PANEL, "serial": "MF1750-LAB-PANEL-0002"}
        other_panel_file = self.root / "other-panel.json"
        other_panel_file.write_bytes(canonical_json_bytes(other_panel))
        other = physical.compile_physical_manifest_from_files(
            self.source_file,
            other_panel_file,
            self.review_file,
            **PROCESS_SCHEDULE,
        )
        self.assertNotEqual(
            first["physical_binding"]["integrity"]["canonical_sha256"],
            other["physical_binding"]["integrity"]["canonical_sha256"],
        )
        self.assertTrue(
            set(first["fixed_actions"].values()).isdisjoint(
                other["fixed_actions"].values()
            )
        )

        other_review = self.root / "other-review.bin"
        other_review.write_bytes(REVIEW_BYTES + b"second review revision\n")
        revised = physical.compile_physical_manifest_from_files(
            self.source_file,
            self.panel_file,
            other_review,
            **PROCESS_SCHEDULE,
        )
        self.assertTrue(
            set(first["fixed_actions"].values()).isdisjoint(
                revised["fixed_actions"].values()
            )
        )

    def test_schedule_changes_rotate_all_identities_and_reject_invalid_values(self) -> None:
        baseline = self._compile()
        for name, schedule in (
            (
                "interval",
                {"minimum_interval_seconds": 151, "planned_cooldown_seconds": 150},
            ),
            (
                "cooldown",
                {"minimum_interval_seconds": 150, "planned_cooldown_seconds": 151},
            ),
            (
                "zero-cooldown",
                {"minimum_interval_seconds": 150, "planned_cooldown_seconds": 0},
            ),
        ):
            with self.subTest(schedule=name):
                changed = physical.compile_physical_manifest_from_files(
                    self.source_file,
                    self.panel_file,
                    self.review_file,
                    **schedule,
                )
                self.assertTrue(
                    set(baseline["fixed_actions"].values()).isdisjoint(
                        changed["fixed_actions"].values()
                    )
                )
                self.assertNotEqual(
                    baseline["operator_manifest_id"], changed["operator_manifest_id"]
                )
        for name, interval, cooldown in (
            ("zero-interval", 0, 150),
            ("negative-interval", -1, 150),
            ("boolean-interval", True, 150),
            ("infinite-interval", float("inf"), 150),
            ("negative-cooldown", 150, -1),
            ("boolean-cooldown", 150, False),
            ("nan-cooldown", 150, float("nan")),
        ):
            with self.subTest(invalid=name), self.assertRaises(
                physical.N2PhysicalCampaignError
            ):
                physical.compile_physical_manifest_from_files(
                    self.source_file,
                    self.panel_file,
                    self.review_file,
                    minimum_interval_seconds=interval,
                    planned_cooldown_seconds=cooldown,
                )
        with self.assertRaises(TypeError):
            physical.compile_physical_manifest_from_files(
                self.source_file,
                self.panel_file,
                self.review_file,
                planned_cooldown_seconds=150,
            )
        with self.assertRaises(TypeError):
            physical.compile_physical_manifest_from_files(
                self.source_file,
                self.panel_file,
                self.review_file,
                minimum_interval_seconds=150,
            )

    def test_rejects_unbound_or_hardware_mismatched_panel(self) -> None:
        for name, panel in (
            ("source-placeholder", dict(frozen.PANEL_CONTRACT)),
            ("embedded-unbound", {**PANEL, "serial": "LAB-UNBOUND-01"}),
            ("wrong-model", {**PANEL, "model": "OTHER-PANEL"}),
            ("wrong-board", {**PANEL, "board_id": "OTHER-BOARD"}),
            ("wrong-pcb", {**PANEL, "pcb_revision": "rev-z9"}),
        ):
            with self.subTest(case=name):
                path = self.root / f"{name}.json"
                path.write_bytes(canonical_json_bytes(panel))
                with self.assertRaises(physical.N2PhysicalCampaignError):
                    physical.compile_physical_manifest_from_files(
                        self.source_file,
                        path,
                        self.review_file,
                        **PROCESS_SCHEDULE,
                    )

    def test_rejects_empty_review_noncanonical_panel_and_source_drift(self) -> None:
        empty = self.root / "empty-review.bin"
        empty.write_bytes(b"")
        with self.assertRaisesRegex(
            physical.N2PhysicalCampaignError, "must not be empty"
        ):
            physical.compile_physical_manifest_from_files(
                self.source_file,
                self.panel_file,
                empty,
                **PROCESS_SCHEDULE,
            )

        pretty_panel = self.root / "pretty-panel.json"
        pretty_panel.write_text(json.dumps(PANEL, indent=2), encoding="utf-8")
        with self.assertRaisesRegex(
            physical.N2PhysicalCampaignError, "canonical JSON"
        ):
            physical.compile_physical_manifest_from_files(
                self.source_file,
                pretty_panel,
                self.review_file,
                **PROCESS_SCHEDULE,
            )

        drifted = deepcopy(self.frozen_manifest)
        drifted["purpose"] = "drifted"
        drifted_source = self.root / "drifted-source.json"
        drifted_source.write_bytes(canonical_json_bytes(drifted))
        with self.assertRaises(physical.N2PhysicalCampaignError):
            physical.compile_physical_manifest_from_files(
                drifted_source,
                self.panel_file,
                self.review_file,
                **PROCESS_SCHEDULE,
            )

    def test_external_review_and_panel_are_reverified_during_validation(self) -> None:
        manifest = self._compile()
        manifest_file = self._write_manifest("operator.json", manifest)
        validated = physical.validate_physical_manifest_file(
            manifest_file,
            self.source_file,
            self.panel_file,
            self.review_file,
        )
        self.assertEqual(validated, manifest)

        changed_review = self.root / "changed-review.bin"
        changed_review.write_bytes(REVIEW_BYTES + b"tampered")
        with self.assertRaisesRegex(
            physical.N2PhysicalCampaignError, "bytes/hash"
        ):
            physical.validate_physical_manifest_file(
                manifest_file,
                self.source_file,
                self.panel_file,
                changed_review,
            )

        changed_panel_file = self.root / "changed-panel.json"
        changed_panel_file.write_bytes(
            canonical_json_bytes({**PANEL, "serial": "MF1750-LAB-PANEL-0009"})
        )
        with self.assertRaisesRegex(
            physical.N2PhysicalCampaignError, "panel file differs"
        ):
            physical.validate_physical_manifest_file(
                manifest_file,
                self.source_file,
                changed_panel_file,
                self.review_file,
            )

    def test_resealed_manifest_tamper_and_old_action_reuse_are_rejected(self) -> None:
        manifest = self._compile()
        tampered = deepcopy(manifest)
        tampered["classification"]["hardware_execution_authorized"] = True
        unsigned = dict(tampered)
        unsigned.pop("integrity")
        tampered["integrity"] = {
            "canonical_sha256": physical._sha256(canonical_json_bytes(unsigned)),
            "canonical_sha256_scope": physical.MANIFEST_HASH_SCOPE,
        }
        with self.assertRaisesRegex(
            physical.N2PhysicalCampaignError, "deterministic materialization"
        ):
            physical.validate_physical_manifest(tampered)

        schedule_tamper = deepcopy(manifest)
        schedule_tamper["operator_process_schedule"][
            "minimum_interval_seconds"
        ] = 151
        unsigned = dict(schedule_tamper)
        unsigned.pop("integrity")
        schedule_tamper["integrity"] = {
            "canonical_sha256": physical._sha256(canonical_json_bytes(unsigned)),
            "canonical_sha256_scope": physical.MANIFEST_HASH_SCOPE,
        }
        with self.assertRaisesRegex(
            physical.N2PhysicalCampaignError, "deterministic materialization"
        ):
            physical.validate_physical_manifest(schedule_tamper)

        reused = deepcopy(manifest)
        old = self.frozen_manifest["p0_campaign_contract"]["actions"][0]
        reused["physical_campaign_contract"]["actions"][0] = deepcopy(old)
        with self.assertRaises(physical.N2PhysicalCampaignError):
            physical.validate_physical_manifest(reused)

    def test_bundle_rejects_mixed_campaign_or_extra_files(self) -> None:
        manifest = self._compile()
        other_panel_file = self.root / "mixed-other-panel.json"
        other_panel_file.write_bytes(
            canonical_json_bytes({**PANEL, "serial": "MF1750-LAB-PANEL-0099"})
        )
        other = physical.compile_physical_manifest_from_files(
            self.source_file,
            other_panel_file,
            self.review_file,
            **PROCESS_SCHEDULE,
        )
        mixed = self.root / "mixed-bundle"
        mixed.mkdir()
        (mixed / physical.OPERATOR_MANIFEST_FILENAME).write_bytes(
            canonical_json_bytes(manifest)
        )
        (mixed / physical.PHYSICAL_CAMPAIGN_FILENAME).write_bytes(
            canonical_json_bytes(other["physical_campaign_contract"])
        )
        with self.assertRaisesRegex(
            physical.N2PhysicalCampaignError, "does not exactly match"
        ):
            physical.read_physical_bundle(
                mixed, binding_review_artifact_file=self.review_file
            )

        (mixed / "unexpected.txt").write_bytes(b"extra")
        with self.assertRaisesRegex(
            physical.N2PhysicalCampaignError, "exactly the canonical"
        ):
            physical.read_physical_bundle(mixed)

    def test_publish_is_canonical_exclusive_and_describe_remains_unauthorized(self) -> None:
        output = self.root / "physical-bundle"
        manifest = physical.publish_physical_bundle(
            self.source_file,
            self.panel_file,
            self.review_file,
            output,
            **PROCESS_SCHEDULE,
        )
        campaign_file = output / physical.PHYSICAL_CAMPAIGN_FILENAME
        manifest_file = output / physical.OPERATOR_MANIFEST_FILENAME
        self.assertEqual(
            campaign_file.read_bytes(),
            canonical_json_bytes(manifest["physical_campaign_contract"]),
        )
        self.assertEqual(manifest_file.read_bytes(), canonical_json_bytes(manifest))
        self.assertEqual(
            physical.read_physical_campaign(campaign_file),
            manifest["physical_campaign_contract"],
        )
        self.assertEqual(
            physical.read_physical_bundle(
                output, binding_review_artifact_file=self.review_file
            ),
            manifest,
        )
        with self.assertRaisesRegex(
            physical.N2PhysicalCampaignError, "already exists"
        ):
            physical.publish_physical_bundle(
                self.source_file,
                self.panel_file,
                self.review_file,
                output,
                **PROCESS_SCHEDULE,
            )
        description = physical.describe_physical_bundle(
            output,
            self.source_file,
            self.panel_file,
            self.review_file,
        )
        self.assertTrue(description["all_action_identities_and_claims_new"])
        self.assertFalse(description["limit_profile_draft_approved"])
        self.assertFalse(description["hardware_execution_authorized"])
        self.assertFalse(description["claim_created"])
        self.assertFalse(description["network_io_performed"])
        self.assertEqual(
            description["physical_campaign_file"]["filename"],
            physical.PHYSICAL_CAMPAIGN_FILENAME,
        )

    def test_standalone_campaign_integrates_with_production_profile_inputs(self) -> None:
        firmware_file = frozen.FIRMWARE_BINARY
        if not firmware_file.is_file():
            self.skipTest("clean CI may omit the exact frozen firmware binary")
        bundle = self.root / "production-profile-bundle"
        manifest = physical.publish_physical_bundle(
            self.source_file,
            self.panel_file,
            self.review_file,
            bundle,
            **PROCESS_SCHEDULE,
        )
        campaign = manifest["physical_campaign_contract"]
        provenance = {
            field: {
                "classification": (
                    production.EXACT_SUPPLIER_DOCUMENT_PROVENANCE
                    if field
                    in {
                        "minimum_start_temperature_c",
                        "maximum_start_temperature_c",
                        "maximum_post_refresh_temperature_c",
                    }
                    else production.OPERATOR_SELECTED_PROCESS_GATE_PROVENANCE
                ),
                "source_document_sha256": production.MF1750_A1_SOURCE_DOCUMENT_SHA256,
            }
            for field in production._LIMIT_FIELDS
        }
        policy = {
            "schema_version": 1,
            "kind": production.SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND,
            "not_a_supplier_rating": True,
            "supervised_only": True,
            "automatic_execution": False,
            "automatic_retry": False,
            "automatic_recovery": False,
            "issuer": "unit-test-lab-process-owner",
            "policy_id": "n2p-physical-positive-150-second-policy",
            "issued_at": "2026-08-07T20:00:00Z",
            "panel_model": PANEL["model"],
            "maximum_usage_snapshot_age_seconds": 7200,
            "limits": {
                "maximum_campaign_visible_refreshes": 8,
                "maximum_session_visible_refreshes": 2,
                "maximum_consecutive_visible_refreshes": 2,
                "minimum_interval_seconds": 150,
                "minimum_cooldown_seconds": 150,
                "minimum_start_temperature_c": 0,
                "maximum_start_temperature_c": 50,
                "maximum_post_refresh_temperature_c": 50,
            },
            "validity": {
                "valid_from": "2026-08-08T01:00:00Z",
                "expires_at": "2026-08-08T03:00:00Z",
            },
            "field_provenance": provenance,
        }
        usage = {
            "schema_version": 1,
            "kind": production.USAGE_EVIDENCE_KIND,
            "evidence_id": "usage-snapshot-physical-0001",
            "campaign_canonical_sha256": campaign["integrity"]["canonical_sha256"],
            "panel": campaign["panel"],
            "firmware": campaign["firmware"],
            "usage": {
                "cumulative_visible_refresh_count": 0,
                "session_visible_refresh_count": 0,
                "consecutive_visible_refresh_count": 0,
                "last_visible_refresh_completed_at": None,
                "snapshot_at": "2026-08-08T00:00:00Z",
            },
        }
        policy_file = self._write_manifest("production-policy.json", policy)
        usage_file = self._write_manifest("production-usage.json", usage)
        campaign_file = bundle / physical.PHYSICAL_CAMPAIGN_FILENAME
        inputs = production.load_production_inputs(
            campaign_file=campaign_file,
            firmware_binary_file=firmware_file,
            supplier_limits_file=policy_file,
            usage_evidence_file=usage_file,
        )
        draft = production.compile_production_draft(
            inputs,
            profile_id="n2p-physical-production-draft",
            profile_version="1.0.0",
        )
        self.assertEqual(inputs.campaign, campaign)
        self.assertEqual(
            [entry["action_identity_sha256"] for entry in draft["action_allowlist"]],
            list(manifest["fixed_actions"].values()),
        )
        self.assertFalse(draft["review"]["approved"])
        draft_file = self._write_manifest("production-draft.json", draft)
        reviewer_key = self.root / "production-reviewer.key"
        reviewer_key.write_bytes(bytes(range(32)))
        approval = production.create_production_approval(
            draft_profile_file=draft_file,
            campaign_file=campaign_file,
            firmware_binary_file=firmware_file,
            supplier_limits_file=policy_file,
            usage_evidence_file=usage_file,
            reviewer_id="unit-test-n2p-process-reviewer",
            reviewed_at="2026-08-08T00:30:00Z",
            reviewer_key_file=reviewer_key,
        )
        review_file = self.root / "production-review.json"
        profile_file = self.root / "production-profile.json"
        production.publish_approval_bundle(
            approval,
            review_artifact_output=review_file,
            profile_output=profile_file,
        )
        report = production.validate_production_profile(
            profile_file=profile_file,
            campaign_file=campaign_file,
            firmware_binary_file=firmware_file,
            supplier_limits_file=policy_file,
            usage_evidence_file=usage_file,
            review_artifact_file=review_file,
            reviewer_key_file=reviewer_key,
            evaluated_at="2026-08-08T01:30:00Z",
        )
        self.assertTrue(report["production_ready"])
        self.assertEqual(
            report["limit_authority_classification"],
            production.SUPERVISED_PROCESS_AUTHORITY_CLASSIFICATION,
        )

    def test_cli_compile_validate_describe_and_requires_explicit_inputs(self) -> None:
        output = self.root / "cli-bundle"
        common = [
            "--source-manifest",
            str(self.source_file),
            "--panel-file",
            str(self.panel_file),
            "--binding-review-artifact",
            str(self.review_file),
        ]
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            exit_code = physical.main(
                [
                    "compile",
                    *common,
                    "--minimum-interval-seconds",
                    "150",
                    "--planned-cooldown-seconds",
                    "150",
                    "--output-dir",
                    str(output),
                ]
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["mode"], "compiled-and-published")
        for command, expected_mode in (("validate", "validated"), ("describe", "describe-only")):
            with self.subTest(command=command):
                stdout = io.StringIO()
                with mock.patch("sys.stdout", stdout):
                    exit_code = physical.main(
                        [command, "--bundle-dir", str(output), *common]
                    )
                self.assertEqual(exit_code, 0)
                result = json.loads(stdout.getvalue())
                self.assertEqual(result["mode"], expected_mode)
                self.assertEqual(result["panel"], PANEL)
        with self.assertRaises(SystemExit):
            physical.parse_args(
                ["compile", *common, "--output-dir", str(self.root / "missing")]
            )
        for option, value in (
            ("--minimum-interval-seconds", "0"),
            ("--minimum-interval-seconds", "true"),
            ("--planned-cooldown-seconds", "false"),
            ("--planned-cooldown-seconds", "-1"),
        ):
            arguments = [
                "compile",
                *common,
                "--minimum-interval-seconds",
                "150",
                "--planned-cooldown-seconds",
                "150",
                "--output-dir",
                str(self.root / f"invalid-{value}"),
            ]
            arguments[arguments.index(option) + 1] = value
            with self.subTest(option=option, value=value), self.assertRaises(SystemExit):
                physical.parse_args(arguments)


if __name__ == "__main__":
    unittest.main()
