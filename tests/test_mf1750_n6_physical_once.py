from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import hashlib
from io import StringIO
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping
import unittest
from unittest.mock import Mock, patch

from host.application.n6_browser_campaign import DEFAULT_MAPPINGS
from host.application.n6_physical_execution import (
    N6PhysicalBrowserController,
    N6PhysicalExecutionError,
    N6PhysicalReceiptPaths,
    N6PhysicalReceiptStore,
    validate_n6_physical_receipt_durable_commit,
)
from host.application.n6_visible_execution import (
    AtomicN6ClaimStore,
    N6HttpRefreshDriver,
)
from host.application import n6_visible_execution as visible_execution
from tests.application_browser_harness import TEST_BUILD_TAG
from tests.test_frame_tool import (
    ScriptedRequester,
    add_valid_busy_trace,
    valid_refresh_responses,
)
from tests.test_n6_physical_execution import (
    CLAIMED_AT,
    COMPLETED_AT,
    INITIAL_LIVE_AT,
    N6PhysicalFixture,
    SequenceClock,
)
from tools import mf1750_n6_physical_once as runner
from tools import mf1750_n6_visible_once as legacy_runner


def _capture_cli_parser() -> argparse.ArgumentParser:
    captured: list[argparse.ArgumentParser] = []

    def capture(
        parser: argparse.ArgumentParser,
        args: list[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> argparse.Namespace:
        del args, namespace
        captured.append(parser)
        return argparse.Namespace()

    with patch.object(argparse.ArgumentParser, "parse_args", new=capture):
        runner.parse_args([])
    if len(captured) != 1:
        raise AssertionError("N6 physical CLI parser capture failed")
    return captured[0]


def _subcommand_parser(
    parser: argparse.ArgumentParser, command: str
) -> argparse.ArgumentParser:
    for action in parser._actions:  # noqa: SLF001
        choices = getattr(action, "choices", None)
        if isinstance(choices, dict) and command in choices:
            selected = choices[command]
            if isinstance(selected, argparse.ArgumentParser):
                return selected
    raise AssertionError(f"missing N6 physical CLI command {command!r}")


def _all_parsers(parser: argparse.ArgumentParser) -> list[argparse.ArgumentParser]:
    output = [parser]
    for action in parser._actions:  # noqa: SLF001
        choices = getattr(action, "choices", None)
        if isinstance(choices, dict):
            for child in choices.values():
                if isinstance(child, argparse.ArgumentParser):
                    output.extend(_all_parsers(child))
    return output


def _minimal_required_argv(
    parser: argparse.ArgumentParser, command: str
) -> list[str]:
    child = _subcommand_parser(parser, command)
    arguments = [command]
    for action in child._actions:  # noqa: SLF001
        if not action.required or not action.option_strings:
            continue
        option = next(
            (
                candidate
                for candidate in action.option_strings
                if candidate.startswith("--")
            ),
            action.option_strings[0],
        )
        arguments.append(option)
        if action.nargs == 0:
            continue
        arguments.append("1" if action.type in {int, float} else "placeholder")
    return arguments


def _validate_namespace(
    *,
    receipt: Path | None,
    receipt_commit: Path | None,
    bundle: Path | None,
    incident: Path | None = None,
    incident_receipt_output: Path | None = None,
    incident_receipt_commit_output: Path | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        command="validate",
        receipt=receipt,
        receipt_commit=receipt_commit,
        bundle=bundle,
        incident=incident,
        incident_receipt_output=incident_receipt_output,
        incident_receipt_commit_output=incident_receipt_commit_output,
        authorization_envelope=Path("authorization.json"),
        runtime_observation_envelope=Path("runtime.json"),
        authorization_evidence=Path("authorization.bin"),
        runtime_observation_evidence=Path("runtime.bin"),
        runtime_trusted_reviewer_key=Path("reviewer.key"),
    )


class N6PhysicalOnceParserAndLegacyTests(unittest.TestCase):
    def test_parser_has_no_operator_time_or_count_injection(self) -> None:
        parser = _capture_cli_parser()
        option_strings = {
            option
            for current in _all_parsers(parser)
            for action in current._actions  # noqa: SLF001
            for option in action.option_strings
        }
        self.assertTrue(
            {
                "--incident",
                "--incident-receipt-output",
                "--incident-receipt-commit-output",
            }.issubset(option_strings)
        )
        forbidden_fragments = {
            "evaluated_at",
            "claimed_at",
            "completed_at",
            "materialized_at",
            "finalized_at",
        }
        for option in option_strings:
            normalized = option.lstrip("-").replace("-", "_")
            self.assertFalse(
                any(fragment in normalized for fragment in forbidden_fragments),
                f"forbidden wall-clock override is registered: {option}",
            )
            self.assertNotIn(
                "count",
                normalized,
                f"forbidden execution-count override is registered: {option}",
            )

        rejected = (
            ("describe", "--evaluated-at"),
            ("serve", "--claimed-at"),
            ("serve", "--completed-at"),
            ("materialize", "--materialized-at"),
            ("finalize", "--finalized-at"),
            ("serve", "--count"),
            ("serve", "--frame-post-count"),
            ("serve", "--retry-count"),
            ("serve", "--recovery-count"),
        )
        for command, option in rejected:
            with self.subTest(command=command, option=option):
                stderr = StringIO()
                arguments = _minimal_required_argv(parser, command)
                with redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
                    runner.parse_args([*arguments, option, "1"])
                self.assertEqual(error.exception.code, 2)
                self.assertIn("unrecognized arguments", stderr.getvalue())

    def test_legacy_serve_is_hard_blocked_before_claim_or_network(self) -> None:
        blocked = Mock(side_effect=AssertionError("forbidden legacy side effect"))
        with (
            patch.object(legacy_runner, "_validated_live_inputs", blocked),
            patch.object(legacy_runner, "_claim_path", blocked),
            patch.object(legacy_runner, "AtomicN6ClaimStore", blocked),
            patch.object(legacy_runner, "N6HttpRefreshDriver", blocked),
            patch.object(legacy_runner, "ApplicationHttpServer", blocked),
        ):
            with self.assertRaisesRegex(
                legacy_runner.N6VisibleOnceToolError,
                "legacy N6 serve is disabled before claim/network",
            ):
                legacy_runner.serve_command(argparse.Namespace())
        self.assertEqual(blocked.call_count, 0)

    def test_validate_bundle_requires_standalone_receipt_and_commit(self) -> None:
        cases = (
            (
                _validate_namespace(
                    receipt=None,
                    receipt_commit=Path("receipt.commit.json"),
                    bundle=Path("bundle.json"),
                ),
                "standalone --receipt",
            ),
            (
                _validate_namespace(
                    receipt=Path("receipt.json"),
                    receipt_commit=None,
                    bundle=Path("bundle.json"),
                ),
                "runtime evidence arguments",
            ),
        )
        for namespace, message in cases:
            with self.subTest(message=message):
                stderr = StringIO()
                validate = Mock(side_effect=AssertionError("validate must not run"))
                with (
                    patch.object(runner, "parse_args", return_value=namespace),
                    patch.object(runner, "validate_command", validate),
                    redirect_stderr(stderr),
                ):
                    self.assertEqual(runner.main([]), 2)
                self.assertEqual(validate.call_count, 0)
                self.assertIn(message, stderr.getvalue())

    def test_validate_incident_is_exclusive_and_requires_both_expected_paths(
        self,
    ) -> None:
        invalid_cases = (
            (
                _validate_namespace(
                    receipt=Path("receipt.json"),
                    receipt_commit=Path("receipt.commit.json"),
                    bundle=None,
                    incident=Path("incident.json"),
                    incident_receipt_output=Path("expected-receipt.json"),
                    incident_receipt_commit_output=Path("expected-commit.json"),
                ),
                "cannot be combined",
            ),
            (
                _validate_namespace(
                    receipt=None,
                    receipt_commit=None,
                    bundle=None,
                    incident=Path("incident.json"),
                    incident_receipt_output=Path("expected-receipt.json"),
                ),
                "requires both expected receipt output paths",
            ),
            (
                _validate_namespace(
                    receipt=None,
                    receipt_commit=None,
                    bundle=None,
                    incident_receipt_output=Path("expected-receipt.json"),
                    incident_receipt_commit_output=Path("expected-commit.json"),
                ),
                "require --incident",
            ),
        )
        for namespace, message in invalid_cases:
            with self.subTest(message=message):
                stderr = StringIO()
                validate = Mock(side_effect=AssertionError("validate must not run"))
                with (
                    patch.object(runner, "parse_args", return_value=namespace),
                    patch.object(runner, "validate_command", validate),
                    redirect_stderr(stderr),
                ):
                    self.assertEqual(runner.main([]), 2)
                self.assertEqual(validate.call_count, 0)
                self.assertIn(message, stderr.getvalue())

        valid = _validate_namespace(
            receipt=None,
            receipt_commit=None,
            bundle=None,
            incident=Path("incident.json"),
            incident_receipt_output=Path("expected-receipt.json"),
            incident_receipt_commit_output=Path("expected-commit.json"),
        )
        validate_output = {
            "schema_version": 1,
            "kind": "mf1750-n6-physical-validate-result",
            "valid": True,
        }
        stdout = StringIO()
        stderr = StringIO()
        with (
            patch.object(runner, "parse_args", return_value=valid),
            patch.object(
                runner,
                "validate_command",
                return_value=validate_output,
            ) as validate,
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            self.assertEqual(runner.main([]), 0, stderr.getvalue())
        validate.assert_called_once_with(valid)
        self.assertEqual(json.loads(stdout.getvalue()), validate_output)


class N6PhysicalOnceDurabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_directory = tempfile.TemporaryDirectory()
        fixture_root = Path(cls.fixture_directory.name).resolve()
        cls.fixture = N6PhysicalFixture(fixture_root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture_directory.cleanup()

    def test_fresh_claim_registry_is_durably_prepared_without_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            legacy_manifest = self.fixture.manifest["legacy_formal_manifest"]
            store = AtomicN6ClaimStore(workspace)
            original = visible_execution.ensure_directory_tree_durable
            with patch.object(
                visible_execution,
                "ensure_directory_tree_durable",
                wraps=original,
            ) as durable_prepare:
                registry = store.prepare_registry(legacy_manifest)
            durable_prepare.assert_called_once()
            self.assertTrue(registry.is_dir())
            self.assertEqual(
                durable_prepare.call_args.kwargs["root"],
                workspace,
            )
            self.assertEqual(store.claim_path(legacy_manifest).parent, registry)
            self.assertFalse(store.claim_path(legacy_manifest).exists())

    def test_serve_uses_repo_root_and_blocking_non_daemon_close_without_io(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            claim_path = workspace / "claims" / "fixed-claim.json"
            receipt_output = workspace / "receipt.json"
            commit_output = workspace / "receipt.commit.json"
            events: list[tuple[Any, ...]] = []
            controller_arguments: dict[str, Any] = {}
            server_box: dict[str, Any] = {}

            class FakeClaimStore:
                def __init__(self, root: Path) -> None:
                    events.append(("claim_store", root))
                    self.root = root

                def prepare_registry(self, manifest: Mapping[str, Any]) -> Path:
                    del manifest
                    events.append(("prepare_registry",))
                    claim_path.parent.mkdir()
                    return claim_path.parent

            class FakeController:
                receipt = None
                receipt_durable_commit = None

                def __init__(self, manifest: Mapping[str, Any], **kwargs: Any) -> None:
                    del manifest
                    events.append(("controller",))
                    controller_arguments.update(kwargs)

            class FakeServer:
                def __init__(self, address: tuple[str, int], runtime: Any) -> None:
                    del runtime
                    events.append(("server", address))
                    self.origin = f"http://{address[0]}:{address[1]}"
                    self.security_token = "test-only-security-token"
                    self.daemon_threads = True
                    self.block_on_close = False
                    self.timeout: float | None = None
                    server_box["value"] = self

                def handle_request(self) -> None:
                    events.append(("handle_request",))
                    raise KeyboardInterrupt

                def server_close(self) -> None:
                    events.append(
                        (
                            "server_close",
                            self.daemon_threads,
                            self.block_on_close,
                        )
                    )

            def fake_driver(device_url: str) -> object:
                events.append(("protocol_driver", device_url))
                return object()

            def fake_runtime(*args: Any, **kwargs: Any) -> object:
                del args, kwargs
                events.append(("runtime",))
                return object()

            args = argparse.Namespace(
                confirm_serve=runner.SERVE_CONFIRMATION,
                bind="127.0.0.1",
                port=18765,
                receipt_output=receipt_output,
                receipt_commit_output=commit_output,
                attempt_id="n6-physical-cli-no-io-attempt",
                device_url="http://127.0.0.1:1",
            )
            stdout = StringIO()
            with (
                patch.object(runner, "_wall_now", return_value=INITIAL_LIVE_AT),
                patch.object(
                    runner,
                    "_load_physical_manifest",
                    return_value=(
                        self.fixture.manifest,
                        self.fixture.sources,
                        self.fixture.production_files,
                        self.fixture.static_files,
                    ),
                ),
                patch.object(
                    runner,
                    "_load_runtime_inputs",
                    return_value=(
                        self.fixture.authorization_envelope,
                        self.fixture.runtime_observation_envelope,
                        self.fixture.runtime_files,
                    ),
                ),
                patch.object(runner, "_claim_path", return_value=claim_path),
                patch.object(runner, "AtomicN6ClaimStore", FakeClaimStore),
                patch.object(runner, "N6HttpRefreshDriver", fake_driver),
                patch.object(runner, "N6PhysicalBrowserController", FakeController),
                patch.object(runner, "ApplicationRuntime", fake_runtime),
                patch.object(runner, "ApplicationHttpServer", FakeServer),
                patch.object(
                    runner,
                    "measured_palette_from_n6_manifest",
                    return_value=object(),
                ),
                patch.object(
                    runner,
                    "measured_gamut_profile_from_n6_manifest",
                    return_value=object(),
                ),
                redirect_stdout(stdout),
            ):
                result = runner.serve_command(args)

            self.assertFalse(result["claim_created"])
            self.assertFalse(result["network_io_performed"])
            self.assertFalse(result["device_io_performed"])
            self.assertEqual(events[0], ("claim_store", runner.REPO_ROOT))
            self.assertLess(
                events.index(("prepare_registry",)),
                events.index(("protocol_driver", args.device_url)),
            )
            self.assertIsInstance(
                controller_arguments["post_claim_receipt_sink"],
                N6PhysicalReceiptStore,
            )
            sink = controller_arguments["post_claim_receipt_sink"]
            self.assertEqual(sink.paths.receipt_output, receipt_output)
            self.assertEqual(sink.paths.receipt_commit_output, commit_output)
            self.assertEqual(
                sink.paths.incident_output,
                claim_path.parent
                / f"{claim_path.name}.N6-PHYSICAL-UNKNOWN.json",
            )
            server = server_box["value"]
            self.assertFalse(server.daemon_threads)
            self.assertTrue(server.block_on_close)
            self.assertIn(("server_close", False, True), events)
            self.assertFalse(claim_path.exists())
            self.assertFalse(receipt_output.exists())
            self.assertFalse(commit_output.exists())
            self.assertFalse(sink.paths.incident_output.exists())

    def test_concrete_store_binds_receipt_sidecar_and_incident_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            paths = N6PhysicalReceiptPaths(
                receipt_output=workspace / "receipt.json",
                receipt_commit_output=workspace / "receipt.commit.json",
                incident_output=workspace / "temporary-placeholder.json",
            )
            claim_store = AtomicN6ClaimStore(workspace)
            legacy_manifest = self.fixture.manifest["legacy_formal_manifest"]
            claim_store.prepare_registry(legacy_manifest)
            claim_path = claim_store.claim_path(legacy_manifest)
            paths = replace(
                paths,
                incident_output=claim_path.parent
                / f"{claim_path.name}.N6-PHYSICAL-UNKNOWN.json",
            )
            receipt_store = N6PhysicalReceiptStore(
                self.fixture.manifest,
                paths=paths,
            )
            responses = valid_refresh_responses(
                self.fixture.artifact.frame,
                build_tag=TEST_BUILD_TAG,
            )
            diagnostic_status, diagnostic_body = responses[
                "/api/diagnostic/report"
            ][0]
            assert isinstance(diagnostic_body, str)
            diagnostic = json.loads(diagnostic_body)
            add_valid_busy_trace(diagnostic)
            responses["/api/diagnostic/report"] = [
                (diagnostic_status, json.dumps(diagnostic))
            ]
            requester = ScriptedRequester(responses)
            protocol_driver = N6HttpRefreshDriver(
                "http://127.0.0.1:1",
                requester=requester,
                poll_interval_s=0.001,
                sleeper=lambda _seconds: None,
            )
            controller = N6PhysicalBrowserController(
                self.fixture.manifest,
                sources=self.fixture.sources,
                production_files=self.fixture.production_files,
                static_evidence_files=self.fixture.static_files,
                authorization_envelope=self.fixture.authorization_envelope,
                runtime_observation_envelope=self.fixture.runtime_observation_envelope,
                runtime_evidence_files=self.fixture.runtime_files,
                claim_store=claim_store,
                protocol_driver=protocol_driver,
                attempt_id="n6-cli-path-binding-attempt",
                post_claim_receipt_sink=receipt_store,
                utc_now=SequenceClock(
                    INITIAL_LIVE_AT,
                    CLAIMED_AT,
                    COMPLETED_AT,
                ),
            )
            self.fixture.prepare_browser(controller)
            self.fixture.arm(controller)
            controller.enqueue(
                DEFAULT_MAPPINGS,
                token_validated=True,
                same_origin_validated=True,
            )
            receipt = controller.receipt
            commit = controller.receipt_durable_commit
            assert receipt is not None
            assert commit is not None
            self.assertTrue(claim_path.is_file())
            self.assertEqual(protocol_driver.frame_post_request_count, 1)
            self.assertEqual(
                requester.calls,
                [
                    ("GET", "/api/version"),
                    ("POST", "/api/frame"),
                    ("GET", "/api/job"),
                    ("GET", "/api/diagnostic/report"),
                ],
            )
            self.assertEqual(controller.receipt_paths, receipt_store.paths)
            validate_n6_physical_receipt_durable_commit(
                commit,
                receipt=receipt,
                paths=paths,
            )
            self.assertEqual(json.loads(paths.receipt_output.read_bytes()), receipt)
            self.assertEqual(
                json.loads(paths.receipt_commit_output.read_bytes()),
                commit,
            )
            expected_path_hashes = {
                "receipt_output": "receipt_output_path_sha256",
                "receipt_commit_output": "receipt_commit_output_path_sha256",
                "incident_output": "postclaim_incident_output_path_sha256",
            }
            for field, commit_key in expected_path_hashes.items():
                path = getattr(paths, field)
                self.assertEqual(
                    commit[commit_key],
                    hashlib.sha256(str(path).encode("utf-8")).hexdigest(),
                )
                wrong_paths = replace(
                    paths,
                    **{field: workspace / f"wrong-{field}.json"},
                )
                with self.assertRaisesRegex(
                    N6PhysicalExecutionError,
                    "binding changed",
                ):
                    validate_n6_physical_receipt_durable_commit(
                        commit,
                        receipt=receipt,
                        paths=wrong_paths,
                    )

            paths.incident_output.write_bytes(b"{}")
            with self.assertRaisesRegex(
                N6PhysicalExecutionError,
                "incident exists",
            ):
                validate_n6_physical_receipt_durable_commit(
                    commit,
                    receipt=receipt,
                    paths=paths,
                )


if __name__ == "__main__":
    unittest.main()
