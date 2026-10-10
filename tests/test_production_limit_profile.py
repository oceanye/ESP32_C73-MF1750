from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.visible_refresh_campaign import (
    CAMPAIGN_KIND,
    build_fixed_action_declaration,
    build_session_contract,
    canonical_json_bytes,
    evaluate_limit_profile,
    seal_campaign_contract,
    seal_limit_profile,
)
from host.visible_refresh_campaign import production_profile as production
from tools import mf1750_limit_profile as cli


EVALUATED_AT = "2026-08-08T01:30:00Z"
REVIEWED_AT = "2026-08-08T00:30:00Z"
MF1750_A1_SOURCE_DOCUMENT = (
    Path(__file__).resolve().parents[1] / "参考资料" / "MF-1750..1).pdf"
)


def _frame(digit: str) -> dict[str, object]:
    return {
        "width": 1024,
        "height": 600,
        "bits_per_pixel": 4,
        "bytes": 307200,
        "sha256": digit * 64,
        "fnv1a": f"0x{int(digit, 16):08X}",
        "controllers": [
            {
                "controller": "CS1",
                "mapping": {
                    "source_half": 0,
                    "flip_x": False,
                    "flip_y": False,
                    "nibble_swap": False,
                },
                "dtm_bytes": 153600,
                "dtm_sha256": "a" * 64,
                "dtm_fnv1a": "0x0000000A",
            },
            {
                "controller": "CS2",
                "mapping": {
                    "source_half": 1,
                    "flip_x": False,
                    "flip_y": False,
                    "nibble_swap": False,
                },
                "dtm_bytes": 153600,
                "dtm_sha256": "b" * 64,
                "dtm_fnv1a": "0x0000000B",
            },
        ],
    }


def _campaign(firmware: bytes, *, serial: str = "MF1750-PHYSICAL-0001") -> dict[str, object]:
    panel = {
        "model": "MF1750-C73",
        "serial": serial,
        "board_id": "ESP32-C73-BOARD-0001",
        "pcb_revision": "rev-a1",
    }
    firmware_contract = {
        "source_commit": "1" * 40,
        "build_tag": "rc2g-production-physical-0001",
        "binary_sha256": hashlib.sha256(firmware).hexdigest(),
        "driver_api": "mf1750-api-v3",
    }
    primer = build_fixed_action_declaration(
        campaign_id="production-dynamic-campaign",
        session_id="physical-session-1",
        cell_id="physical-cell-1",
        action_id="physical-map-primer",
        phase="map-primer",
        frame=_frame("1"),
    )
    target = build_fixed_action_declaration(
        campaign_id="production-dynamic-campaign",
        session_id="physical-session-1",
        cell_id="physical-cell-1",
        action_id="physical-target",
        phase="target",
        frame=_frame("2"),
        prior_action_identity_sha256=primer["action_identity_sha256"],
        prior_scope="same_cell",
        minimum_interval_since_prior_seconds=20,
    )
    session = build_session_contract(
        session_id="physical-session-1",
        cell_id="physical-cell-1",
        power_mode="controller_fresh_boot",
        planned_cooldown_seconds=60,
        final_power_off_required=False,
        action_identity_sha256s=[
            primer["action_identity_sha256"],
            target["action_identity_sha256"],
        ],
    )
    return seal_campaign_contract(
        {
            "schema_version": 1,
            "kind": CAMPAIGN_KIND,
            "campaign_id": "production-dynamic-campaign",
            "panel": panel,
            "firmware": firmware_contract,
            "actions": [primer, target],
            "sessions": [session],
            "classification": {
                "offline_compiled": True,
                "hardware_execution_authorized": False,
                "automatic_execution": False,
                "automatic_retry": False,
                "automatic_recovery": False,
                "network_io_performed": False,
                "device_io_performed": False,
            },
        }
    )


class ProductionLimitProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.firmware_bytes = b"physical-rc2g-firmware\x00" * 64
        self.campaign = _campaign(self.firmware_bytes)
        self.campaign_file = self._write_json("campaign.json", self.campaign)
        self.firmware_file = self.root / "firmware.bin"
        self.firmware_file.write_bytes(self.firmware_bytes)
        self.supplier = {
            "schema_version": 1,
            "kind": production.SUPPLIER_LIMITS_KIND,
            "supplier_id": "mf1750-supplier-production",
            "document_id": "mf1750-c73-limits-2026-08",
            "issued_at": "2026-08-07T20:00:00Z",
            "panel_model": "MF1750-C73",
            "maximum_usage_snapshot_age_seconds": 7200,
            "limits": {
                "maximum_campaign_visible_refreshes": 2,
                "maximum_session_visible_refreshes": 2,
                "maximum_consecutive_visible_refreshes": 2,
                "minimum_interval_seconds": 10,
                "minimum_cooldown_seconds": 30,
                "minimum_start_temperature_c": 10,
                "maximum_start_temperature_c": 40,
                "maximum_post_refresh_temperature_c": 45,
            },
            "validity": {
                "valid_from": "2026-08-08T01:00:00Z",
                "expires_at": "2026-08-08T03:00:00Z",
            },
        }
        self.supplier_file = self._write_json("supplier.json", self.supplier)
        self.usage = {
            "schema_version": 1,
            "kind": production.USAGE_EVIDENCE_KIND,
            "evidence_id": "usage-snapshot-physical-0001",
            "campaign_canonical_sha256": self.campaign["integrity"][
                "canonical_sha256"
            ],
            "panel": self.campaign["panel"],
            "firmware": self.campaign["firmware"],
            "usage": {
                "cumulative_visible_refresh_count": 0,
                "session_visible_refresh_count": 0,
                "consecutive_visible_refresh_count": 0,
                "last_visible_refresh_completed_at": None,
                "snapshot_at": "2026-08-08T00:00:00Z",
            },
        }
        self.usage_file = self._write_json("usage.json", self.usage)
        self.key_file = self.root / "trusted-reviewer.key"
        self.key_file.write_bytes(bytes(range(32)))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_json(
        self, name: str, value: object, *, canonical: bool = True
    ) -> Path:
        path = self.root / name
        payload = (
            canonical_json_bytes(value)
            if canonical
            else json.dumps(value, indent=2).encode("utf-8")
        )
        path.write_bytes(payload)
        return path

    def _inputs(self) -> dict[str, Path]:
        return {
            "campaign_file": self.campaign_file,
            "firmware_binary_file": self.firmware_file,
            "supplier_limits_file": self.supplier_file,
            "usage_evidence_file": self.usage_file,
        }

    def _policy(self) -> dict[str, object]:
        provenance = {}
        for field in production._LIMIT_FIELDS:
            classification = (
                production.EXACT_SUPPLIER_DOCUMENT_PROVENANCE
                if field
                in {
                    "minimum_start_temperature_c",
                    "maximum_start_temperature_c",
                }
                else production.OPERATOR_SELECTED_PROCESS_GATE_PROVENANCE
            )
            provenance[field] = {
                "classification": classification,
                "source_document_sha256": (
                    production.MF1750_A1_SOURCE_DOCUMENT_SHA256
                ),
            }
        return {
            "schema_version": 1,
            "kind": production.SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND,
            "not_a_supplier_rating": True,
            "supervised_only": True,
            "automatic_execution": False,
            "automatic_retry": False,
            "automatic_recovery": False,
            "issuer": "trusted-lab-process-owner",
            "policy_id": "mf1750-a1-supervised-process-test-v1",
            "issued_at": "2026-08-07T20:00:00Z",
            "panel_model": "MF1750-C73",
            "maximum_usage_snapshot_age_seconds": 7200,
            "limits": {
                "maximum_campaign_visible_refreshes": 2,
                "maximum_session_visible_refreshes": 2,
                "maximum_consecutive_visible_refreshes": 2,
                "minimum_interval_seconds": 10,
                "minimum_cooldown_seconds": 30,
                "minimum_start_temperature_c": 0,
                "maximum_start_temperature_c": 50,
                "maximum_post_refresh_temperature_c": 45,
            },
            "validity": {
                "valid_from": "2026-08-08T01:00:00Z",
                "expires_at": "2026-08-08T03:00:00Z",
            },
            "field_provenance": provenance,
        }

    def _policy_inputs(self, name: str = "process-policy.json") -> dict[str, Path]:
        policy_file = self._write_json(name, self._policy())
        return {
            **self._inputs(),
            "supplier_limits_file": policy_file,
        }

    def _policy_approval(
        self,
    ) -> tuple[
        production.ApprovalBundle,
        dict[str, Path],
        Path,
        Path,
    ]:
        inputs = self._policy_inputs()
        draft = production.compile_production_draft_from_files(
            **inputs,
            profile_id="supervised-process-policy-profile",
            profile_version="1.0.0",
        )
        draft_file = self._write_json("policy-draft.json", draft)
        bundle = production.create_production_approval(
            draft_profile_file=draft_file,
            **inputs,
            reviewer_id="trusted-policy-reviewer",
            reviewed_at=REVIEWED_AT,
            reviewer_key_file=self.key_file,
        )
        review_file = self.root / "policy-review.json"
        profile_file = self.root / "policy-profile.json"
        production.publish_approval_bundle(
            bundle,
            review_artifact_output=review_file,
            profile_output=profile_file,
        )
        return bundle, inputs, review_file, profile_file

    def _draft(self, name: str = "draft.json") -> tuple[dict[str, object], Path]:
        draft = production.compile_production_draft_from_files(
            **self._inputs(),
            profile_id="physical-production-profile",
            profile_version="1.0.0",
        )
        return draft, self._write_json(name, draft)

    def _approval(
        self,
    ) -> tuple[production.ApprovalBundle, Path, Path, Path]:
        _draft, draft_file = self._draft()
        bundle = production.create_production_approval(
            draft_profile_file=draft_file,
            **self._inputs(),
            reviewer_id="trusted-physical-reviewer",
            reviewed_at=REVIEWED_AT,
            reviewer_key_file=self.key_file,
        )
        artifact_file = self.root / "review-artifact.json"
        profile_file = self.root / "reviewed-profile.json"
        production.publish_approval_bundle(
            bundle,
            review_artifact_output=artifact_file,
            profile_output=profile_file,
        )
        return bundle, draft_file, artifact_file, profile_file

    def test_draft_uses_every_dynamic_action_and_is_never_approved(self) -> None:
        draft, draft_file = self._draft()
        self.assertEqual(draft["panel"], self.campaign["panel"])
        self.assertEqual(draft["firmware"], self.campaign["firmware"])
        self.assertEqual(len(draft["action_allowlist"]), len(self.campaign["actions"]))
        self.assertEqual(
            draft["limit_authority_kind"], production.SUPPLIER_LIMITS_KIND
        )
        self.assertEqual(
            draft["limit_authority_classification"],
            production.SUPPLIER_LIMIT_AUTHORITY_CLASSIFICATION,
        )
        self.assertEqual(
            [entry["action_identity_sha256"] for entry in draft["action_allowlist"]],
            [action["action_identity_sha256"] for action in self.campaign["actions"]],
        )
        self.assertEqual(
            draft["usage"]["evidence_sha256"],
            hashlib.sha256(self.usage_file.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            draft["review"],
            {
                "approved": False,
                "reviewer_id": None,
                "reviewed_at": None,
                "review_artifact_sha256": None,
            },
        )
        decision = evaluate_limit_profile(draft, evaluated_at=EVALUATED_AT)
        self.assertFalse(decision.hardware_ready)
        self.assertIn("review_not_approved", decision.reasons)
        report = production.validate_production_profile(
            profile_file=draft_file, **self._inputs(), evaluated_at=EVALUATED_AT
        )
        self.assertTrue(report["deep_bindings_valid"])
        self.assertFalse(report["production_ready"])

    def test_authenticated_approval_and_deep_validation(self) -> None:
        bundle, _draft, artifact_file, profile_file = self._approval()
        artifact_sha = hashlib.sha256(artifact_file.read_bytes()).hexdigest()
        self.assertEqual(
            bundle.profile["review"]["review_artifact_sha256"], artifact_sha
        )
        self.assertEqual(
            bundle.review_artifact["usage_evidence_file_sha256"],
            hashlib.sha256(self.usage_file.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            bundle.review_artifact["firmware_binary_sha256"],
            hashlib.sha256(self.firmware_bytes).hexdigest(),
        )
        self.assertEqual(
            bundle.review_artifact["usage_canonical_sha256"],
            hashlib.sha256(canonical_json_bytes(bundle.profile["usage"])).hexdigest(),
        )
        self.assertEqual(
            bundle.review_artifact["limits_canonical_sha256"],
            hashlib.sha256(canonical_json_bytes(bundle.profile["limits"])).hexdigest(),
        )
        self.assertEqual(
            bundle.review_artifact["authentication"]["key_id"],
            hashlib.sha256(self.key_file.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            bundle.review_artifact["limit_authority_kind"],
            production.SUPPLIER_LIMITS_KIND,
        )
        self.assertEqual(
            bundle.review_artifact["limit_authority_file_sha256"],
            bundle.review_artifact["supplier_limits_file_sha256"],
        )
        validated = production.load_validated_production_profile(
            profile_file=profile_file,
            **self._inputs(),
            review_artifact_file=artifact_file,
            reviewer_key_file=self.key_file,
            evaluated_at=EVALUATED_AT,
        )
        report = validated.report
        self.assertTrue(report["deep_bindings_valid"])
        self.assertTrue(report["approved"])
        self.assertTrue(report["production_ready"])
        self.assertEqual(report["reasons"], [])
        self.assertEqual(
            report["limit_authority_kind"], production.SUPPLIER_LIMITS_KIND
        )
        self.assertEqual(
            report["limit_authority_classification"],
            production.SUPPLIER_LIMIT_AUTHORITY_CLASSIFICATION,
        )
        self.assertEqual(
            report["limit_authority_file_sha256"],
            report["supplier_limits_file_sha256"],
        )
        self.assertEqual(validated.profile_file.payload, profile_file.read_bytes())
        self.assertEqual(
            validated.inputs.campaign_file.payload, self.campaign_file.read_bytes()
        )
        self.assertEqual(
            validated.inputs.firmware_binary.payload, self.firmware_file.read_bytes()
        )
        self.assertEqual(
            validated.review_artifact_file.payload, artifact_file.read_bytes()
        )
        self.assertEqual(
            validated.reviewer_key_id,
            hashlib.sha256(self.key_file.read_bytes()).hexdigest(),
        )

        stale = production.validate_production_profile(
            profile_file=profile_file,
            **self._inputs(),
            review_artifact_file=artifact_file,
            reviewer_key_file=self.key_file,
            evaluated_at="2026-08-08T02:30:00Z",
        )
        self.assertFalse(stale["production_ready"])
        self.assertIn("usage_snapshot_stale", stale["reasons"])

    def test_legacy_supplier_profile_and_review_shapes_remain_accepted(self) -> None:
        current, _current_file = self._draft("current-with-authority.json")
        legacy_payload = deepcopy(current)
        legacy_payload.pop("integrity")
        legacy_payload.pop("limit_authority_kind")
        legacy_payload.pop("limit_authority_classification")
        legacy_draft = seal_limit_profile(legacy_payload)
        legacy_draft_file = self._write_json("legacy-draft.json", legacy_draft)
        bundle = production.create_production_approval(
            draft_profile_file=legacy_draft_file,
            **self._inputs(),
            reviewer_id="trusted-legacy-reviewer",
            reviewed_at=REVIEWED_AT,
            reviewer_key_file=self.key_file,
        )
        self.assertNotIn("limit_authority_kind", bundle.profile)
        self.assertNotIn("limit_authority_kind", bundle.review_artifact)
        legacy_review = self.root / "legacy-review.json"
        legacy_profile = self.root / "legacy-profile.json"
        production.publish_approval_bundle(
            bundle,
            review_artifact_output=legacy_review,
            profile_output=legacy_profile,
        )
        report = production.validate_production_profile(
            profile_file=legacy_profile,
            **self._inputs(),
            review_artifact_file=legacy_review,
            reviewer_key_file=self.key_file,
            evaluated_at=EVALUATED_AT,
        )
        self.assertTrue(report["production_ready"])
        self.assertEqual(
            report["limit_authority_kind"], production.SUPPLIER_LIMITS_KIND
        )

    def test_arbitrary_64hex_cannot_replace_usage_or_review_evidence(self) -> None:
        bundle, _draft, artifact_file, _profile_file = self._approval()
        for field, fake_hash in (
            (("usage", "evidence_sha256"), "0" * 64),
            (("review", "review_artifact_sha256"), "f" * 64),
        ):
            payload = deepcopy(bundle.profile)
            payload.pop("integrity")
            payload[field[0]][field[1]] = fake_hash
            forged = seal_limit_profile(payload)
            forged_file = self._write_json(f"forged-{field[0]}.json", forged)
            with self.subTest(field=field), self.assertRaises(
                production.ProductionProfileError
            ):
                production.validate_production_profile(
                    profile_file=forged_file,
                    **self._inputs(),
                    review_artifact_file=artifact_file,
                    reviewer_key_file=self.key_file,
                    evaluated_at=EVALUATED_AT,
                )

    def test_wrong_source_file_and_post_approval_tamper_are_rejected(self) -> None:
        _bundle, _draft, artifact_file, profile_file = self._approval()
        wrong_usage = deepcopy(self.usage)
        wrong_usage["evidence_id"] = "another-real-file"
        wrong_usage_file = self._write_json("wrong-usage.json", wrong_usage)
        with self.assertRaises(production.ProductionProfileError):
            production.validate_production_profile(
                profile_file=profile_file,
                campaign_file=self.campaign_file,
                firmware_binary_file=self.firmware_file,
                supplier_limits_file=self.supplier_file,
                usage_evidence_file=wrong_usage_file,
                review_artifact_file=artifact_file,
                reviewer_key_file=self.key_file,
                evaluated_at=EVALUATED_AT,
            )
        self.supplier_file.write_bytes(self.supplier_file.read_bytes() + b" ")
        with self.assertRaises(production.ProductionProfileError):
            production.validate_production_profile(
                profile_file=profile_file,
                **self._inputs(),
                review_artifact_file=artifact_file,
                reviewer_key_file=self.key_file,
                evaluated_at=EVALUATED_AT,
            )

    def test_review_tamper_and_untrusted_key_are_rejected(self) -> None:
        bundle, _draft, _artifact_file, profile_file = self._approval()
        tampered = deepcopy(bundle.review_artifact)
        tampered["reviewer_id"] = "forged-reviewer"
        tampered_file = self._write_json("tampered-review.json", tampered)
        tampered_profile_payload = deepcopy(bundle.profile)
        tampered_profile_payload.pop("integrity")
        tampered_profile_payload["review"]["review_artifact_sha256"] = hashlib.sha256(
            tampered_file.read_bytes()
        ).hexdigest()
        tampered_profile = seal_limit_profile(tampered_profile_payload)
        tampered_profile_file = self._write_json(
            "tampered-review-profile.json", tampered_profile
        )
        with self.assertRaisesRegex(
            production.ProductionProfileError, "signature is invalid"
        ):
            production.validate_production_profile(
                profile_file=tampered_profile_file,
                **self._inputs(),
                review_artifact_file=tampered_file,
                reviewer_key_file=self.key_file,
                evaluated_at=EVALUATED_AT,
            )
        wrong_key = self.root / "wrong-reviewer.key"
        wrong_key.write_bytes(b"wrong-trust-anchor" * 4)
        with self.assertRaisesRegex(production.ProductionProfileError, "key_id"):
            production.validate_production_profile(
                profile_file=profile_file,
                **self._inputs(),
                review_artifact_file=self.root / "review-artifact.json",
                reviewer_key_file=wrong_key,
                evaluated_at=EVALUATED_AT,
            )

    def test_missing_numeric_data_remains_blocked_draft(self) -> None:
        incomplete = deepcopy(self.supplier)
        incomplete["limits"]["maximum_post_refresh_temperature_c"] = None
        incomplete_file = self._write_json("incomplete-supplier.json", incomplete)
        inputs = {
            **self._inputs(),
            "supplier_limits_file": incomplete_file,
        }
        draft = production.compile_production_draft_from_files(
            **inputs,
            profile_id="incomplete-production-profile",
            profile_version="1.0.0",
        )
        draft_file = self._write_json("incomplete-draft.json", draft)
        decision = evaluate_limit_profile(draft, evaluated_at=EVALUATED_AT)
        self.assertFalse(decision.hardware_ready)
        self.assertIn(
            "critical_null:limits.maximum_post_refresh_temperature_c",
            decision.reasons,
        )
        with self.assertRaisesRegex(production.ProductionProfileError, "cannot be approved"):
            production.create_production_approval(
                draft_profile_file=draft_file,
                **inputs,
                reviewer_id="trusted-physical-reviewer",
                reviewed_at=REVIEWED_AT,
                reviewer_key_file=self.key_file,
            )

    def test_process_policy_requires_truthful_markers_and_cannot_masquerade(self) -> None:
        base = self._policy()
        for field in (
            "not_a_supplier_rating",
            "supervised_only",
            "automatic_execution",
            "automatic_retry",
            "automatic_recovery",
        ):
            with self.subTest(omitted=field):
                value = deepcopy(base)
                value.pop(field)
                path = self._write_json(f"policy-missing-{field}.json", value)
                with self.assertRaisesRegex(
                    production.ProductionProfileError, "keys differ"
                ):
                    production.compile_production_draft_from_files(
                        **{**self._inputs(), "supplier_limits_file": path},
                        profile_id="must-fail",
                        profile_version="1.0.0",
                    )
        for field, wrong in (
            ("not_a_supplier_rating", False),
            ("supervised_only", False),
            ("automatic_execution", True),
            ("automatic_retry", True),
            ("automatic_recovery", True),
        ):
            with self.subTest(wrong_marker=field):
                value = deepcopy(base)
                value[field] = wrong
                path = self._write_json(f"policy-wrong-{field}.json", value)
                with self.assertRaisesRegex(
                    production.ProductionProfileError, field
                ):
                    production.compile_production_draft_from_files(
                        **{**self._inputs(), "supplier_limits_file": path},
                        profile_id="must-fail",
                        profile_version="1.0.0",
                    )

        disguised = deepcopy(base)
        disguised["kind"] = production.SUPPLIER_LIMITS_KIND
        disguised_file = self._write_json("policy-disguised-as-supplier.json", disguised)
        with self.assertRaisesRegex(production.ProductionProfileError, "keys differ"):
            production.compile_production_draft_from_files(
                **{**self._inputs(), "supplier_limits_file": disguised_file},
                profile_id="must-fail",
                profile_version="1.0.0",
            )
        supplier_disguised = deepcopy(self.supplier)
        supplier_disguised["kind"] = (
            production.SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND
        )
        supplier_disguised_file = self._write_json(
            "supplier-disguised-as-policy.json", supplier_disguised
        )
        with self.assertRaisesRegex(production.ProductionProfileError, "keys differ"):
            production.compile_production_draft_from_files(
                **{
                    **self._inputs(),
                    "supplier_limits_file": supplier_disguised_file,
                },
                profile_id="must-fail",
                profile_version="1.0.0",
            )

    def test_process_policy_provenance_sha_and_numeric_types_fail_closed(self) -> None:
        cases = []
        missing = self._policy()
        missing["field_provenance"].pop("minimum_cooldown_seconds")
        cases.append(("missing-provenance", missing, "cover every limit"))
        wrong_sha = self._policy()
        wrong_sha["field_provenance"]["maximum_start_temperature_c"][
            "source_document_sha256"
        ] = "0" * 64
        cases.append(("wrong-document", wrong_sha, "wrong source document"))
        false_supplier_rating = self._policy()
        false_supplier_rating["field_provenance"][
            "maximum_campaign_visible_refreshes"
        ]["classification"] = production.EXACT_SUPPLIER_DOCUMENT_PROVENANCE
        cases.append(("false-supplier-rating", false_supplier_rating, "supplier rating"))
        wrong_exact_value = self._policy()
        wrong_exact_value["limits"]["maximum_start_temperature_c"] = 49
        cases.append(
            (
                "wrong-exact-value",
                wrong_exact_value,
                "does not match the source document value",
            )
        )
        boolean_limit = self._policy()
        boolean_limit["limits"]["minimum_interval_seconds"] = True
        cases.append(("boolean-limit", boolean_limit, "non-negative finite number"))
        boolean_age = self._policy()
        boolean_age["maximum_usage_snapshot_age_seconds"] = True
        cases.append(("boolean-age", boolean_age, "non-negative finite number"))
        for name, policy, expected in cases:
            with self.subTest(case=name):
                path = self._write_json(f"{name}.json", policy)
                with self.assertRaisesRegex(production.ProductionProfileError, expected):
                    production.compile_production_draft_from_files(
                        **{**self._inputs(), "supplier_limits_file": path},
                        profile_id="must-fail",
                        profile_version="1.0.0",
                    )

    def test_process_policy_approval_deep_binding_and_time_gates(self) -> None:
        bundle, inputs, review_file, profile_file = self._policy_approval()
        policy_file = inputs["supplier_limits_file"]
        policy_sha = hashlib.sha256(policy_file.read_bytes()).hexdigest()
        self.assertEqual(
            bundle.profile["limit_authority_kind"],
            production.SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND,
        )
        self.assertEqual(
            bundle.profile["limit_authority_classification"],
            production.SUPERVISED_PROCESS_AUTHORITY_CLASSIFICATION,
        )
        self.assertNotIn("supplier_limits_file_sha256", bundle.review_artifact)
        self.assertEqual(
            bundle.review_artifact["limit_authority_file_sha256"], policy_sha
        )
        report = production.validate_production_profile(
            profile_file=profile_file,
            **inputs,
            review_artifact_file=review_file,
            reviewer_key_file=self.key_file,
            evaluated_at=EVALUATED_AT,
        )
        self.assertTrue(report["production_ready"])
        self.assertEqual(
            report["limit_authority_kind"],
            production.SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND,
        )
        self.assertEqual(
            report["limit_authority_classification"],
            production.SUPERVISED_PROCESS_AUTHORITY_CLASSIFICATION,
        )
        self.assertEqual(report["limit_authority_file_sha256"], policy_sha)
        self.assertIsNone(report["supplier_limits_file_sha256"])

        stale = production.validate_production_profile(
            profile_file=profile_file,
            **inputs,
            review_artifact_file=review_file,
            reviewer_key_file=self.key_file,
            evaluated_at="2026-08-08T02:30:00Z",
        )
        self.assertFalse(stale["production_ready"])
        self.assertIn("usage_snapshot_stale", stale["reasons"])
        expired = production.validate_production_profile(
            profile_file=profile_file,
            **inputs,
            review_artifact_file=review_file,
            reviewer_key_file=self.key_file,
            evaluated_at="2026-08-08T03:00:00Z",
        )
        self.assertFalse(expired["production_ready"])
        self.assertIn("profile_expired", expired["reasons"])

        tampered = self._policy()
        tampered["limits"]["minimum_cooldown_seconds"] = 31
        tampered_file = self._write_json("tampered-policy-after-review.json", tampered)
        with self.assertRaises(production.ProductionProfileError):
            production.validate_production_profile(
                profile_file=profile_file,
                **{**inputs, "supplier_limits_file": tampered_file},
                review_artifact_file=review_file,
                reviewer_key_file=self.key_file,
                evaluated_at=EVALUATED_AT,
            )

        tampered_review = deepcopy(bundle.review_artifact)
        tampered_review["limit_authority_file_sha256"] = "0" * 64
        tampered_review_file = self._write_json(
            "tampered-policy-review.json", tampered_review
        )
        tampered_profile_payload = deepcopy(bundle.profile)
        tampered_profile_payload.pop("integrity")
        tampered_profile_payload["review"]["review_artifact_sha256"] = hashlib.sha256(
            tampered_review_file.read_bytes()
        ).hexdigest()
        tampered_profile_file = self._write_json(
            "tampered-policy-profile.json",
            seal_limit_profile(tampered_profile_payload),
        )
        with self.assertRaisesRegex(production.ProductionProfileError, "signature"):
            production.validate_production_profile(
                profile_file=tampered_profile_file,
                **inputs,
                review_artifact_file=tampered_review_file,
                reviewer_key_file=self.key_file,
                evaluated_at=EVALUATED_AT,
            )

    def test_policy_template_selects_no_values_and_cli_accepts_neutral_alias(self) -> None:
        template = production.build_supervised_experimental_policy_template(
            issuer="operator-must-complete",
            policy_id="incomplete-policy-template",
            issued_at="2026-08-08T00:00:00Z",
            panel_model="MF1750-C73",
        )
        self.assertTrue(template["not_a_supplier_rating"])
        self.assertTrue(all(value is None for value in template["limits"].values()))
        self.assertIsNone(template["maximum_usage_snapshot_age_seconds"])
        self.assertTrue(
            all(
                record["classification"] is None
                for record in template["field_provenance"].values()
            )
        )
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.parse_args(
                [
                    "policy-template",
                    "--issuer",
                    "operator-must-complete",
                    "--policy-id",
                    "missing-source-must-fail",
                    "--issued-at",
                    "2026-08-08T00:00:00Z",
                    "--panel-model",
                    "MF1750-C73",
                    "--output",
                    str(self.root / "missing-source.json"),
                ]
            )

        template_file = self.root / "cli-policy-template.json"
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(io.StringIO()):
            self.assertEqual(
                cli.main(
                    [
                        "policy-template",
                        "--issuer",
                        "operator-must-complete",
                        "--policy-id",
                        "cli-incomplete-policy-template",
                        "--issued-at",
                        "2026-08-08T00:00:00Z",
                        "--panel-model",
                        "MF1750-C73",
                        "--source-document",
                        str(MF1750_A1_SOURCE_DOCUMENT),
                        "--output",
                        str(template_file),
                    ]
                ),
                0,
            )
        rendered = output.getvalue()
        self.assertIn('"approved": false', rendered)
        self.assertIn('"numeric_limit_values_selected": false', rendered)
        self.assertNotIn("approved-profile", rendered)
        verified_source = production.verify_mf1750_a1_source_document(
            MF1750_A1_SOURCE_DOCUMENT
        )
        self.assertEqual(
            verified_source.sha256,
            production.MF1750_A1_SOURCE_DOCUMENT_SHA256,
        )
        with self.assertRaisesRegex(
            production.ProductionProfileError, "classification is invalid"
        ):
            production.compile_production_draft_from_files(
                **{
                    **self._inputs(),
                    "supplier_limits_file": template_file,
                },
                profile_id="incomplete-template-must-not-run",
                profile_version="1.0.0",
            )

        policy_file = self._write_json("cli-complete-policy.json", self._policy())
        draft_file = self.root / "cli-policy-draft.json"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(
                cli.main(
                    [
                        "draft",
                        "--campaign",
                        str(self.campaign_file),
                        "--firmware-binary",
                        str(self.firmware_file),
                        "--limit-authority",
                        str(policy_file),
                        "--usage-evidence",
                        str(self.usage_file),
                        "--profile-id",
                        "cli-policy-profile",
                        "--profile-version",
                        "1.0.0",
                        "--output",
                        str(draft_file),
                    ]
                ),
                0,
            )
        draft = json.loads(draft_file.read_text(encoding="utf-8"))
        self.assertFalse(draft["review"]["approved"])
        self.assertEqual(
            draft["limit_authority_kind"],
            production.SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND,
        )

        wrong_source = self.root / "wrong-source-document.pdf"
        wrong_source.write_bytes(b"not the exact MF-1750 A1 PDF")
        rejected_output = self.root / "wrong-source-template.json"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(
                cli.main(
                    [
                        "policy-template",
                        "--issuer",
                        "operator-must-complete",
                        "--policy-id",
                        "wrong-source-must-fail",
                        "--issued-at",
                        "2026-08-08T00:00:00Z",
                        "--panel-model",
                        "MF1750-C73",
                        "--source-document",
                        str(wrong_source),
                        "--output",
                        str(rejected_output),
                    ]
                ),
                2,
            )
        self.assertFalse(rejected_output.exists())

    def test_unbound_campaign_wrong_firmware_and_subset_allowlist_fail(self) -> None:
        unbound = _campaign(self.firmware_bytes, serial="UNBOUND-N2P-OFFLINE")
        unbound_file = self._write_json("unbound-campaign.json", unbound)
        with self.assertRaisesRegex(production.ProductionProfileError, "unbound"):
            production.compile_production_draft_from_files(
                **{**self._inputs(), "campaign_file": unbound_file},
                profile_id="must-fail",
                profile_version="1.0.0",
            )
        wrong_firmware = self.root / "wrong-firmware.bin"
        wrong_firmware.write_bytes(b"not-the-campaign-build")
        with self.assertRaisesRegex(production.ProductionProfileError, "firmware binary"):
            production.compile_production_draft_from_files(
                **{**self._inputs(), "firmware_binary_file": wrong_firmware},
                profile_id="must-fail",
                profile_version="1.0.0",
            )
        draft, _draft_file = self._draft()
        subset_payload = deepcopy(draft)
        subset_payload.pop("integrity")
        subset_payload["action_allowlist"] = subset_payload["action_allowlist"][:1]
        subset = seal_limit_profile(subset_payload)
        subset_file = self._write_json("subset-draft.json", subset)
        with self.assertRaisesRegex(production.ProductionProfileError, "exact deterministic"):
            production.create_production_approval(
                draft_profile_file=subset_file,
                **self._inputs(),
                reviewer_id="trusted-physical-reviewer",
                reviewed_at=REVIEWED_AT,
                reviewer_key_file=self.key_file,
            )

    def test_toctou_and_symlink_inputs_fail_closed(self) -> None:
        real_reader = production._read_descriptor_bytes

        def mutate_during_read(descriptor: int, *, maximum_bytes: int, label: str) -> bytes:
            payload = real_reader(
                descriptor, maximum_bytes=maximum_bytes, label=label
            )
            status = os.stat(self.firmware_file)
            os.utime(
                self.firmware_file,
                ns=(status.st_atime_ns, status.st_mtime_ns + 1_000_000_000),
            )
            return payload

        with mock.patch.object(
            production, "_read_descriptor_bytes", side_effect=mutate_during_read
        ), self.assertRaisesRegex(production.ProductionProfileError, "changed"):
            production.read_local_regular_file(
                self.firmware_file, label="TOCTOU firmware", maximum_bytes=4096
            )

        link = self.root / "usage-link.json"
        try:
            link.symlink_to(self.usage_file)
        except OSError:
            return
        with self.assertRaisesRegex(production.ProductionProfileError, "symlink|reparse"):
            production.compile_production_draft_from_files(
                **{**self._inputs(), "usage_evidence_file": link},
                profile_id="must-fail",
                profile_version="1.0.0",
            )

    def test_publish_is_no_clobber_and_concurrency_safe(self) -> None:
        output = self.root / "single-output.bin"
        production.publish_new_bytes(output, b"first", label="single output")
        with self.assertRaisesRegex(production.ProductionProfileError, "already exists"):
            production.publish_new_bytes(output, b"second", label="single output")
        self.assertEqual(output.read_bytes(), b"first")

        raced = self.root / "raced-output.bin"

        def publish(value: bytes) -> bool:
            try:
                production.publish_new_bytes(raced, value, label="raced output")
                return True
            except production.ProductionProfileError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(publish, (b"left", b"right")))
        self.assertEqual(outcomes.count(True), 1)
        self.assertIn(raced.read_bytes(), (b"left", b"right"))

        bundle, _draft, _artifact, _profile = self._approval()
        blocked_profile = self.root / "blocked-profile.json"
        blocked_profile.write_bytes(b"existing")
        new_artifact = self.root / "new-review-artifact.json"
        with self.assertRaisesRegex(production.ProductionProfileError, "already exists"):
            production.publish_approval_bundle(
                bundle,
                review_artifact_output=new_artifact,
                profile_output=blocked_profile,
            )
        self.assertFalse(new_artifact.exists())
        self.assertEqual(blocked_profile.read_bytes(), b"existing")

        pair_review = self.root / "raced-review.json"
        pair_profile = self.root / "raced-profile.json"

        def publish_pair(_index: int) -> bool:
            try:
                production.publish_approval_bundle(
                    bundle,
                    review_artifact_output=pair_review,
                    profile_output=pair_profile,
                )
                return True
            except production.ProductionProfileError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            pair_outcomes = list(pool.map(publish_pair, (0, 1)))
        self.assertEqual(pair_outcomes.count(True), 1)
        self.assertEqual(pair_review.read_bytes(), bundle.review_artifact_bytes)
        self.assertEqual(pair_profile.read_bytes(), bundle.profile_bytes)

    def test_cli_draft_approve_validate_and_describe(self) -> None:
        draft = self.root / "cli-draft.json"
        review = self.root / "cli-review.json"
        profile = self.root / "cli-profile.json"
        common = [
            "--campaign",
            str(self.campaign_file),
            "--firmware-binary",
            str(self.firmware_file),
            "--supplier-limits",
            str(self.supplier_file),
            "--usage-evidence",
            str(self.usage_file),
        ]
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(io.StringIO()):
            self.assertEqual(
                cli.main(
                    [
                        "draft",
                        *common,
                        "--profile-id",
                        "cli-production-profile",
                        "--profile-version",
                        "1.0.0",
                        "--output",
                        str(draft),
                    ]
                ),
                0,
            )
            self.assertEqual(
                cli.main(
                    [
                        "approve",
                        *common,
                        "--draft-profile",
                        str(draft),
                        "--reviewer-id",
                        "trusted-cli-reviewer",
                        "--reviewed-at",
                        REVIEWED_AT,
                        "--review-key",
                        str(self.key_file),
                        "--review-artifact-output",
                        str(review),
                        "--output",
                        str(profile),
                    ]
                ),
                0,
            )
            self.assertEqual(
                cli.main(
                    [
                        "validate",
                        *common,
                        "--profile",
                        str(profile),
                        "--review-artifact",
                        str(review),
                        "--review-key",
                        str(self.key_file),
                    ]
                ),
                0,
            )
            self.assertEqual(
                cli.main(
                    [
                        "describe",
                        *common,
                        "--profile",
                        str(profile),
                        "--review-artifact",
                        str(review),
                        "--review-key",
                        str(self.key_file),
                        "--evaluated-at",
                        EVALUATED_AT,
                        "--require-ready",
                    ]
                ),
                0,
            )
        self.assertTrue(draft.is_file())
        self.assertTrue(review.is_file())
        self.assertTrue(profile.is_file())
        rendered = output.getvalue()
        self.assertIn('"production_ready": true', rendered)
        self.assertNotIn(self.key_file.read_bytes().hex(), rendered)


if __name__ == "__main__":
    unittest.main()
