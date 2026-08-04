from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import run_host_tests


REPO_ROOT = Path(__file__).resolve().parents[1]


def _passing_suite() -> unittest.TestSuite:
    class PassingTest(unittest.TestCase):
        def runTest(self) -> None:
            self.assertEqual(2 + 2, 4)

    return unittest.TestSuite([PassingTest()])


def _failing_suite() -> unittest.TestSuite:
    class FailingTest(unittest.TestCase):
        def runTest(self) -> None:
            self.fail("intentional unit-test failure")

    return unittest.TestSuite([FailingTest()])


def _skipped_suite() -> unittest.TestSuite:
    class SkippedTest(unittest.TestCase):
        def runTest(self) -> None:
            self.skipTest("intentional full-suite skip")

    return unittest.TestSuite([SkippedTest()])


class HostTestReportTests(unittest.TestCase):
    def _run_cli_with_suite(
        self,
        suite: unittest.TestSuite,
        output: Path,
        *extra_args: str,
    ) -> tuple[int, dict[str, object]]:
        with mock.patch.object(run_host_tests, "discover_suite", return_value=suite):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                status = run_host_tests.main(
                    ["--output", str(output), *extra_args]
                )
        return status, json.loads(output.read_text(encoding="utf-8"))

    def test_success_result_is_serialized_without_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "pass.json"
            with mock.patch.dict(
                os.environ, {"HOST_REPORT_SECRET_SENTINEL": "must-not-leak"}
            ):
                status, report = self._run_cli_with_suite(
                    _passing_suite(), output
                )

            self.assertEqual(status, 0)
            self.assertEqual(report["schema_version"], 1)
            self.assertEqual(report["kind"], "mf1750_host_unittest_report")
            self.assertTrue(report["passed"])
            self.assertFalse(report["hardware_tested"])
            self.assertEqual(report["tests_run"], 1)
            self.assertEqual(report["tests_executed"], 1)
            self.assertFalse(report["suite_empty"])
            self.assertFalse(report["all_tests_skipped"])
            self.assertEqual(report["failures"], 0)
            self.assertEqual(report["errors"], 0)
            self.assertEqual(report["failure_details"], [])
            self.assertEqual(report["error_details"], [])
            self.assertIn("version", report["python"])
            self.assertNotIn(
                "must-not-leak", json.dumps(report, ensure_ascii=False)
            )

    def test_failure_is_serialized_and_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "fail.json"
            status, report = self._run_cli_with_suite(
                _failing_suite(), output
            )

            self.assertEqual(status, 1)
            self.assertFalse(report["passed"])
            self.assertEqual(report["tests_run"], 1)
            self.assertEqual(report["failures"], 1)
            self.assertEqual(len(report["failure_details"]), 1)
            self.assertIn(
                "intentional unit-test failure",
                report["failure_details"][0]["traceback"],
            )

    def test_empty_discovery_is_failed_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "empty.json"
            status, report = self._run_cli_with_suite(
                unittest.TestSuite(), output
            )

            self.assertEqual(status, 1)
            self.assertFalse(report["passed"])
            self.assertEqual(report["tests_run"], 0)
            self.assertEqual(report["tests_executed"], 0)
            self.assertTrue(report["suite_empty"])
            self.assertFalse(report["all_tests_skipped"])
            self.assertEqual(report["failures"], 0)
            self.assertEqual(report["errors"], 0)

    def test_all_skipped_discovery_is_failed_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "skipped.json"
            status, report = self._run_cli_with_suite(
                _skipped_suite(), output
            )

            self.assertEqual(status, 1)
            self.assertFalse(report["passed"])
            self.assertEqual(report["tests_run"], 1)
            self.assertEqual(report["tests_executed"], 0)
            self.assertFalse(report["suite_empty"])
            self.assertTrue(report["all_tests_skipped"])
            self.assertEqual(report["skipped"], 1)

    def test_system_exit_from_discovery_writes_failed_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "system-exit.json"
            with mock.patch.object(
                run_host_tests, "discover_suite", side_effect=SystemExit(0)
            ):
                with contextlib.redirect_stdout(
                    io.StringIO()
                ), contextlib.redirect_stderr(io.StringIO()):
                    status = run_host_tests.main(["--output", str(output)])

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(status, 2)
            self.assertFalse(report["passed"])
            self.assertEqual(report["tests_run"], 0)
            self.assertEqual(report["errors"], 1)
            self.assertIn("SystemExit: 0", report["error_details"][0]["traceback"])

    def test_existing_output_requires_explicit_force(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "existing.json"
            output.write_text("old", encoding="utf-8")
            discovery = mock.Mock(
                return_value=_passing_suite()
            )
            with mock.patch.object(run_host_tests, "discover_suite", discovery):
                with contextlib.redirect_stderr(io.StringIO()):
                    status = run_host_tests.main(["--output", str(output)])

            self.assertEqual(status, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "old")
            discovery.assert_not_called()

            status, report = self._run_cli_with_suite(
                _passing_suite(), output, "--force"
            )
            self.assertEqual(status, 0)
            self.assertTrue(report["passed"])

    def test_frozen_production_output_is_rejected_before_write(self) -> None:
        output = run_host_tests.PRODUCTION_DIRECTORY / "host-test-report.json"
        with self.assertRaises(run_host_tests.OutputSafetyError):
            run_host_tests.validate_output_path(output, force=True)
        self.assertFalse(output.exists())

    def test_hard_link_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            output = root / "alias.json"
            source.write_text("frozen-like-content", encoding="utf-8")
            try:
                os.link(source, output)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"hard links unavailable: {error}")

            with self.assertRaises(run_host_tests.OutputSafetyError):
                run_host_tests.validate_output_path(output, force=True)
            self.assertEqual(source.read_text(encoding="utf-8"), "frozen-like-content")

    def test_cli_parser_accepts_output_and_force(self) -> None:
        arguments = run_host_tests.parse_args(
            ["--output", "custom-report.json", "--force"]
        )
        self.assertEqual(arguments.output, "custom-report.json")
        self.assertTrue(arguments.force)


class CiHostReportConfigurationTests(unittest.TestCase):
    def test_ci_runs_reporter_and_always_uploads_both_reports(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "python tools/run_host_tests.py --output host-test-report.json --force",
            workflow,
        )
        self.assertIn("python tools/validate_ci_reports.py", workflow)
        self.assertIn("REPORT_OUTCOME", workflow)
        self.assertIn("host-test-report.json", workflow)
        self.assertIn("repo-contract-report.json", workflow)
        self.assertGreaterEqual(workflow.count("if: always()"), 2)


if __name__ == "__main__":
    unittest.main()
