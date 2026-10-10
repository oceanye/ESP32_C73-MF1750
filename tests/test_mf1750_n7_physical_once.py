from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.visible_refresh_campaign import canonical_json_bytes
from host.visible_refresh_campaign import production_profile as production
from tools import mf1750_n7_physical_analyzer as analyzer
from tools import mf1750_n7_physical_campaign as physical
from tools import mf1750_n7_physical_once as runner
from tools import mf1750_n7_spi_sweep_campaign as frozen
from tests.test_mf1750_n7_spi_sweep_campaign import fake_firmware
from tests.test_mf1750_n7_spi_sweep_once import (
    ScriptedRequester,
    responses_for_first,
    responses_for_next,
    serial_log,
)


PANEL = {
    "model": "MF1750-C73",
    "serial": "MF1750-M009F-PHYSICAL-N7-0001",
    "board_id": "ESP32-C73",
    "pcb_revision": "rev-a1",
}


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class WallClock:
    def __init__(self, *values: str) -> None:
        self.values = [_dt(value) for value in values]
        self.index = 0

    def __call__(self) -> datetime:
        if self.index < len(self.values):
            value = self.values[self.index]
            self.index += 1
            return value
        return self.values[-1]


class N7PhysicalOnceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        firmware = fake_firmware()
        self.bytes_patch = mock.patch.object(
            frozen, "FIRMWARE_EXPECTED_BYTES", len(firmware)
        )
        self.sha_patch = mock.patch.object(
            frozen, "FIRMWARE_EXPECTED_SHA256", frozen.sha256(firmware)
        )
        self.bytes_patch.start()
        self.sha_patch.start()
        self.source = self.root / "source"
        frozen.write_campaign_directory(
            self.source,
            firmware,
            created_at_utc="2026-08-08T00:00:00Z",
        )
        self.panel = self.write_json("panel.json", PANEL)
        self.binding_review = self.root / "panel-binding-review.bin"
        self.binding_review.write_bytes(b"trusted N7 panel binding evidence bytes\n")
        self.bundle = self.root / "physical"
        physical.publish_physical_bundle(
            self.source,
            self.panel,
            self.binding_review,
            self.bundle,
            minimum_interval_seconds=150,
            planned_cooldown_seconds=150,
        )
        self.manifest = json.loads(
            (self.bundle / physical.MANIFEST_FILENAME).read_text("utf-8")
        )
        self.key = self.root / "trusted-reviewer.key"
        self.key.write_bytes(bytes(range(32)))
        self.claims = self.root / "claims"
        self.registry_patch = mock.patch.object(
            runner, "DEFAULT_CLAIM_REGISTRY", self.claims
        )
        self.registry_patch.start()

    def tearDown(self) -> None:
        self.registry_patch.stop()
        self.sha_patch.stop()
        self.bytes_patch.stop()
        self.temporary.cleanup()

    def write_json(self, name: str, value: object) -> Path:
        path = self.root / name
        path.write_bytes(canonical_json_bytes(value))
        return path

    def _policy(self, *, valid_from: str) -> dict[str, object]:
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
        return {
            "schema_version": 1,
            "kind": production.SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND,
            "not_a_supplier_rating": True,
            "supervised_only": True,
            "automatic_execution": False,
            "automatic_retry": False,
            "automatic_recovery": False,
            "issuer": "trusted-n7-test-process-owner",
            "policy_id": f"n7-policy-{valid_from}",
            "issued_at": "2026-08-07T20:00:00Z",
            "panel_model": PANEL["model"],
            "maximum_usage_snapshot_age_seconds": 7200,
            "limits": {
                "maximum_campaign_visible_refreshes": 5,
                "maximum_session_visible_refreshes": 1,
                "maximum_consecutive_visible_refreshes": 1,
                "minimum_interval_seconds": 100,
                "minimum_cooldown_seconds": 100,
                "minimum_start_temperature_c": 0,
                "maximum_start_temperature_c": 50,
                "maximum_post_refresh_temperature_c": 50,
            },
            "validity": {
                "valid_from": valid_from,
                "expires_at": "2026-09-01T00:00:00Z",
            },
            "field_provenance": provenance,
        }

    def production_inputs(
        self,
        frequency_hz: int,
        *,
        cumulative: int,
        last_visible: str | None,
        snapshot_at: str,
        reviewed_at: str,
        valid_from: str,
    ) -> dict[str, Path]:
        prefix = f"{frequency_hz // 1_000_000}mhz"
        campaign = self.manifest["physical_campaign"]
        authority = self.write_json(
            f"{prefix}-authority.json", self._policy(valid_from=valid_from)
        )
        usage = self.write_json(
            f"{prefix}-usage.json",
            {
                "schema_version": 1,
                "kind": production.USAGE_EVIDENCE_KIND,
                "evidence_id": f"n7-{prefix}-usage",
                "campaign_canonical_sha256": campaign["integrity"][
                    "canonical_sha256"
                ],
                "panel": campaign["panel"],
                "firmware": campaign["firmware"],
                "usage": {
                    "cumulative_visible_refresh_count": cumulative,
                    "session_visible_refresh_count": 0,
                    "consecutive_visible_refresh_count": 0,
                    "last_visible_refresh_completed_at": last_visible,
                    "snapshot_at": snapshot_at,
                },
            },
        )
        common = {
            "campaign_file": self.bundle / physical.PHYSICAL_CAMPAIGN_FILENAME,
            "firmware_binary_file": self.source / "firmware.bin",
            "supplier_limits_file": authority,
            "usage_evidence_file": usage,
        }
        draft = production.compile_production_draft_from_files(
            **common,
            profile_id=f"n7-{prefix}-production-profile",
            profile_version="1.0.0",
        )
        draft_file = self.write_json(f"{prefix}-draft.json", draft)
        approved = production.create_production_approval(
            draft_profile_file=draft_file,
            **common,
            reviewer_id="trusted-n7-physical-reviewer",
            reviewed_at=reviewed_at,
            reviewer_key_file=self.key,
        )
        review = self.root / f"{prefix}-review.json"
        profile = self.root / f"{prefix}-profile.json"
        production.publish_approval_bundle(
            approved,
            review_artifact_output=review,
            profile_output=profile,
        )
        return {
            "profile_file": profile,
            "limit_authority_file": authority,
            "usage_evidence_file": usage,
            "profile_review_artifact_file": review,
            "reviewer_key_file": self.key,
        }

    def common(self, production_inputs: dict[str, Path]) -> dict[str, object]:
        return {
            "physical_bundle_dir": self.bundle,
            "source_campaign_directory": self.source,
            "panel_file": self.panel,
            "panel_binding_review_file": self.binding_review,
            "minimum_interval_seconds": 150,
            "planned_cooldown_seconds": 150,
            **production_inputs,
        }

    def confirmations(self, frequency_hz: int) -> dict[str, bool]:
        return {key: True for key in runner._expected_confirmation_keys(frequency_hz)}

    def tokens(
        self, frequency_hz: int, common: dict[str, object], *, evaluated_at: str
    ) -> tuple[runner._Context, dict[str, str]]:
        context = runner._load_context(
            frequency_hz, **common, evaluated_at=evaluated_at
        )
        return context, {
            "authorization_confirmation": runner.required_action_authorization(
                frequency_hz, context.action["action_identity_sha256"]
            ),
            "panel_confirmation": runner.required_panel_confirmation(context),
            "profile_confirmation": runner.required_profile_confirmation(context),
        }

    def finalize(self, directory: Path, frequency_hz: int, finalized_at: str) -> dict:
        serial = self.root / f"{frequency_hz}-serial.log"
        scope = self.root / f"{frequency_hz}-scope.bin"
        job_id = frozen.FREQUENCIES.index(frequency_hz) + 1
        serial.write_bytes(serial_log(frequency_hz, job_id))
        scope.write_bytes(f"scope-{frequency_hz}".encode())
        return dict(
            runner.finalize_physical_result(
                directory,
                serial,
                scope,
                reviewer_key_file=self.key,
                measured_sclk_hz=float(frequency_hz),
                supply_voltage_v=3.3,
                current_limit_a=1.0,
                peak_current_a=0.2,
                max_temperature_c=30,
                visual_pass=True,
                cv_pass=True,
                thermal_pass=True,
                acoustic_pass=True,
                sclk_pass=True,
                notes="synthetic physical evidence",
                now=WallClock(finalized_at),
            )
        )

    def test_first_action_claims_before_network_posts_once_and_deep_finalizes(self) -> None:
        production_inputs = self.production_inputs(
            1_000_000,
            cumulative=0,
            last_visible=None,
            snapshot_at="2026-08-08T01:59:00Z",
            reviewed_at="2026-08-08T02:00:00Z",
            valid_from="2026-08-08T02:00:10Z",
        )
        common = self.common(production_inputs)
        context, tokens = self.tokens(
            1_000_000, common, evaluated_at="2026-08-08T02:00:30.000Z"
        )
        description = runner.describe_physical_action(
            1_000_000,
            **common,
            now=WallClock("2026-08-08T02:00:30Z"),
        )
        self.assertEqual(
            description["action_identity_sha256"],
            context.action["action_identity_sha256"],
        )
        self.assertFalse(self.claims.exists())

        scripted = ScriptedRequester(responses_for_first())
        claim_path = self.claims / f"{context.action['action_identity_sha256']}.json"

        def claimed_request(*args: object, **kwargs: object) -> tuple[int, str]:
            self.assertTrue(claim_path.is_file())
            return scripted(*args, **kwargs)

        destination = self.root / "result-1mhz"
        live = runner.run_physical_action_once(
            1_000_000,
            destination,
            "http://device",
            **common,
            **tokens,
            panel_power_off_seconds=150,
            start_temperature_c=25,
            confirmations=self.confirmations(1_000_000),
            requester=claimed_request,
            now=WallClock(
                "2026-08-08T02:00:30Z",
                "2026-08-08T02:00:30Z",
                "2026-08-08T02:01:00Z",
            ),
            sleeper=lambda _seconds: None,
        )
        self.assertEqual(live["request_audit"]["visible_post_count"], 1)
        final = self.finalize(destination, 1_000_000, "2026-08-08T02:01:20Z")
        self.assertEqual(final["outcome"], "PASS")
        validated = runner.validate_physical_result(
            destination, reviewer_key_file=self.key
        )
        self.assertEqual(validated["state"], "PASS")
        self.assertTrue(validated["deep_validation_pass"])
        self.assertEqual(scripted.calls.count(("POST", frozen.ROUTES[1_000_000])), 1)

    def test_preclaim_tokens_schedule_freshness_and_key_fail_closed(self) -> None:
        production_inputs = self.production_inputs(
            1_000_000,
            cumulative=0,
            last_visible=None,
            snapshot_at="2026-08-08T01:59:00Z",
            reviewed_at="2026-08-08T02:00:00Z",
            valid_from="2026-08-08T02:00:10Z",
        )
        common = self.common(production_inputs)
        _context, tokens = self.tokens(
            1_000_000, common, evaluated_at="2026-08-08T02:00:30.000Z"
        )
        cases = (
            ("token", {**tokens, "authorization_confirmation": "wrong"}, 150, WallClock("2026-08-08T02:00:30Z"), "authorization"),
            ("schedule", tokens, 120, WallClock("2026-08-08T02:00:30Z"), "schedule"),
            (
                "freshness",
                tokens,
                150,
                WallClock("2026-08-08T02:00:30Z", "2026-08-08T02:06:00Z"),
                "stale",
            ),
        )
        for label, selected_tokens, off_seconds, wall, expected in cases:
            with self.subTest(label=label):
                scripted = ScriptedRequester(responses_for_first())
                with self.assertRaisesRegex(runner.N7PhysicalOnceError, expected):
                    runner.run_physical_action_once(
                        1_000_000,
                        self.root / f"blocked-{label}",
                        "http://device",
                        **common,
                        **selected_tokens,
                        panel_power_off_seconds=off_seconds,
                        start_temperature_c=25,
                        confirmations=self.confirmations(1_000_000),
                        requester=scripted,
                        now=wall,
                    )
                self.assertEqual(scripted.calls, [])
        self.assertFalse(self.claims.exists())

        wrong_key = self.root / "wrong.key"
        wrong_key.write_bytes(b"z" * 32)
        wrong = dict(common)
        wrong["reviewer_key_file"] = wrong_key
        with self.assertRaisesRegex(runner.N7PhysicalOnceError, "production profile"):
            runner.describe_physical_action(
                1_000_000,
                **wrong,
                now=WallClock("2026-08-08T02:00:30Z"),
            )

    def test_run_cli_maps_every_exact_confirmation_without_live_io(self) -> None:
        frequency_hz = 2_000_000
        flags = [
            f"--confirm-{key.replace('_', '-')}"
            for key in sorted(runner._expected_confirmation_keys(frequency_hz))
        ]
        args = runner.parse_args(
            [
                "run",
                "new-result",
                "--physical-bundle",
                "physical",
                "--source-campaign-dir",
                "source",
                "--panel",
                "panel.json",
                "--binding-review",
                "binding.bin",
                "--minimum-interval-seconds",
                "150",
                "--planned-cooldown-seconds",
                "150",
                "--profile",
                "profile.json",
                "--limit-authority",
                "authority.json",
                "--usage-evidence",
                "usage.json",
                "--profile-review",
                "review.json",
                "--reviewer-key",
                "reviewer.key",
                "--frequency-hz",
                str(frequency_hz),
                "--predecessor-result-dir",
                "previous",
                "--url",
                "http://device",
                "--authorization-confirmation",
                "action-token",
                "--panel-confirmation",
                "panel-token",
                "--profile-confirmation",
                "profile-token",
                "--panel-power-off-seconds",
                "150",
                "--start-temperature-c",
                "25",
                *flags,
            ]
        )
        self.assertEqual(args.command, "run")
        self.assertTrue(all(runner._cli_confirmations(args).values()))

    def test_second_action_requires_exact_prior_and_usage_chain(self) -> None:
        first_inputs = self.production_inputs(
            1_000_000,
            cumulative=0,
            last_visible=None,
            snapshot_at="2026-08-08T01:59:00Z",
            reviewed_at="2026-08-08T02:00:00Z",
            valid_from="2026-08-08T02:00:10Z",
        )
        first_common = self.common(first_inputs)
        first_context, first_tokens = self.tokens(
            1_000_000, first_common, evaluated_at="2026-08-08T02:00:30.000Z"
        )
        first_dir = self.root / "chain-1mhz"
        first_scripted = ScriptedRequester(responses_for_first())
        first_live = runner.run_physical_action_once(
            1_000_000,
            first_dir,
            "http://device",
            **first_common,
            **first_tokens,
            panel_power_off_seconds=150,
            start_temperature_c=25,
            confirmations=self.confirmations(1_000_000),
            requester=first_scripted,
            now=WallClock(
                "2026-08-08T02:00:30Z",
                "2026-08-08T02:00:30Z",
                "2026-08-08T02:01:00Z",
            ),
            sleeper=lambda _seconds: None,
        )
        self.finalize(first_dir, 1_000_000, "2026-08-08T02:01:20Z")

        second_inputs = self.production_inputs(
            2_000_000,
            cumulative=1,
            last_visible=first_live["protocol_completed_at"],
            snapshot_at="2026-08-08T02:03:00Z",
            reviewed_at="2026-08-08T02:03:05Z",
            valid_from="2026-08-08T02:03:10Z",
        )
        second_common = self.common(second_inputs)
        second_context, second_tokens = self.tokens(
            2_000_000, second_common, evaluated_at="2026-08-08T02:04:00.000Z"
        )
        self.assertEqual(
            second_context.action["identity"]["prior"]["action_identity_sha256"],
            first_context.action["action_identity_sha256"],
        )
        scripted = ScriptedRequester(
            responses_for_next(2_000_000, first_live["protocol"])
        )
        second_dir = self.root / "chain-2mhz"
        runner.run_physical_action_once(
            2_000_000,
            second_dir,
            "http://device",
            **second_common,
            **second_tokens,
            panel_power_off_seconds=150,
            start_temperature_c=25,
            confirmations=self.confirmations(2_000_000),
            predecessor_result_dir=first_dir,
            requester=scripted,
            now=WallClock(
                "2026-08-08T02:04:00Z",
                "2026-08-08T02:04:00Z",
                "2026-08-08T02:05:00Z",
            ),
            sleeper=lambda _seconds: None,
        )
        self.assertEqual(
            self.finalize(second_dir, 2_000_000, "2026-08-08T02:05:20Z")[
                "outcome"
            ],
            "PASS",
        )
        self.assertEqual(
            runner.validate_physical_result(second_dir, reviewer_key_file=self.key)[
                "state"
            ],
            "PASS",
        )

        copied_prior = second_dir / runner.PRIOR_FINAL_FILENAME
        changed = json.loads(copied_prior.read_text("utf-8"))
        changed["observation"]["visual_pass"] = False
        copied_prior.write_bytes(canonical_json_bytes(changed))
        with self.assertRaises(runner.N7PhysicalOnceError):
            runner.validate_physical_result(second_dir, reviewer_key_file=self.key)

    def test_full_five_action_chain_is_deeply_analyzed(self) -> None:
        schedules = (
            ("2026-08-08T02:00:30Z", "2026-08-08T02:01:00Z"),
            ("2026-08-08T02:04:00Z", "2026-08-08T02:05:00Z"),
            ("2026-08-08T02:08:00Z", "2026-08-08T02:09:00Z"),
            ("2026-08-08T02:12:00Z", "2026-08-08T02:13:00Z"),
            ("2026-08-08T02:16:00Z", "2026-08-08T02:17:00Z"),
        )
        result_directories: list[Path] = []
        previous_directory: Path | None = None
        previous_live: dict | None = None
        for index, (frequency_hz, (evaluated_at, completed_at)) in enumerate(
            zip(frozen.FREQUENCIES, schedules, strict=True)
        ):
            evaluated = _dt(evaluated_at)
            snapshot_at = runner._timestamp(
                evaluated.replace(second=0) - timedelta(seconds=60)
            )
            reviewed_at = runner._timestamp(
                evaluated.replace(second=0) - timedelta(seconds=20)
            )
            valid_from = runner._timestamp(
                evaluated.replace(second=0) - timedelta(seconds=10)
            )
            production_inputs = self.production_inputs(
                frequency_hz,
                cumulative=index,
                last_visible=(
                    None
                    if previous_live is None
                    else previous_live["protocol_completed_at"]
                ),
                snapshot_at=snapshot_at,
                reviewed_at=reviewed_at,
                valid_from=valid_from,
            )
            common = self.common(production_inputs)
            _context, tokens = self.tokens(
                frequency_hz,
                common,
                evaluated_at=evaluated_at.replace("Z", ".000Z"),
            )
            scripted = ScriptedRequester(
                responses_for_first(frequency_hz)
                if previous_live is None
                else responses_for_next(frequency_hz, previous_live["protocol"])
            )
            directory = self.root / f"full-{frequency_hz}"
            live = runner.run_physical_action_once(
                frequency_hz,
                directory,
                "http://device",
                **common,
                **tokens,
                panel_power_off_seconds=150,
                start_temperature_c=25,
                confirmations=self.confirmations(frequency_hz),
                predecessor_result_dir=previous_directory,
                requester=scripted,
                now=WallClock(evaluated_at, evaluated_at, completed_at),
                sleeper=lambda _seconds: None,
            )
            finalized_at = runner._timestamp(
                _dt(completed_at) + timedelta(seconds=20)
            )
            self.assertEqual(
                self.finalize(directory, frequency_hz, finalized_at)["outcome"],
                "PASS",
            )
            self.assertEqual(
                scripted.calls.count(("POST", frozen.ROUTES[frequency_hz])), 1
            )
            result_directories.append(directory)
            previous_directory = directory
            previous_live = live

        analysis = analyzer.analyze_physical_sweep(
            result_directories, reviewer_key_file=self.key
        )
        self.assertEqual(analysis["counts"]["visible_actions"], 5)
        self.assertEqual(analysis["counts"]["unique_claims"], 5)
        self.assertEqual(analysis["descriptive_summary"]["highest_passed_hz"], 10_000_000)
        self.assertEqual(analysis["classification"]["qualification_state"], "NOT_QUALIFIED")
        self.assertEqual(
            len({row["limit_authority_file_sha256"] for row in analysis["rows"]}),
            5,
        )
        with self.assertRaises(analyzer.N7PhysicalAnalyzerError):
            analyzer.analyze_physical_sweep(
                [*result_directories[:-1], result_directories[0]],
                reviewer_key_file=self.key,
            )


if __name__ == "__main__":
    unittest.main()
